You are pre-screening draft evaluation questions for a retrieval QA project over U.S. government
budget, economic and energy documents. A model drafted each question from one CHUNK of a document.
For each candidate in the attached packet, give a verdict the owner will verify by eye. You do not
make the decision; the owner does, so every verdict must quote the evidence.

THE ONLY REFERENCE IS THE CHUNK printed under each candidate. Do not use outside knowledge, do not
compute, round, convert or infer values. If the chunk does not show it, it does not count.

## Checks for table and prose candidates (and supplement, which is a table candidate)
1. ANSWER: Find the cell (table) or phrase (prose) the question asks for. GOLD must be that value,
   character for character as printed in the chunk (same digits, commas, signs, words). A value
   from a neighbouring row or column is wrong.
2. UNIT AND PERIOD (numbers): the unit (e.g. "in millions of dollars") and the period (e.g. the
   "2025 est." column) must both be printed in this chunk, and the question must state both.
   Prose: the question must state whatever the phrase depends on (who, what, when).
3. SELF-CONTAINED: someone with the whole corpus but not this chunk must be able to tell what is
   asked. It must name the account/series/programme/table/document by something printed in the
   chunk (an identification code, series name, programme, heading). "This table", "the chunk",
   "the account above", "the document" fail.
4. ONE ANSWER: exactly one cell or phrase in the chunk answers it. If two columns or rows fit (year
   or unit missing, two similar rows), it fails.
5. LENGTH: the question is 8 to 40 words.
Also fail a candidate whose chunk is only a heading, a table of contents or boilerplate, or whose
question is about the document's formatting rather than its content.

## Verdict rules
- A = all checks pass.
- E = it fails only because the question is missing a few words that the chunk supplies (year,
  unit, account code, series name), or GOLD is the wrong cell/format of a value that IS in the
  chunk. Give the exact replacement text. Edits are small: add or correct words; never write a
  different question. If the fix is more than that, it is R.
- R = anything else. Reason from this list: wrong cell, answer not in chunk, unit not in chunk,
  period not in chunk, ambiguous, not self-contained, heading only, draft failed, length.
- Mark UNSURE: yes when the evidence is unclear (garbled table, merged cells, two plausible
  readings). The owner looks at those closely.

## Controls (stratum "control"; no chunk)
These must be UNANSWERABLE. Judge only well-formedness against the corpus document list at the end
of the packet: A if it reads like a normal question about this kind of data, is self-contained,
8 to 40 words, and its kind fits (absent_entity: asks about something no listed document covers by
its title; out_of_range_period: asks about a period outside the listed documents' dates). R if it
is vague, is answerable from a listed document's title/date, or the kind does not fit. Never E.
(Whether the corpus really lacks the answer is checked later by reading retrieval results.)

## Output — one block per candidate, in packet order, nothing else
ID: t01
VERDICT: A | E | R
EVIDENCE: row "<row label as printed>" × column "<column header as printed>" = "<value as printed>";
          unit "<as printed>"   (prose: quote the sentence containing the answer)
EDIT QUESTION: <full new question, only if E and the question changes; else ->
EDIT GOLD: <exact value as printed, only if E and gold changes; else ->
REASON: <from the list, only if R; else ->
UNSURE: yes | no

After all blocks, give a one-line count: A n / E n / R n / UNSURE n.
