You decompose an answer into claims for a fact-checking study. The answer was written from source documents (U.S. government budget, economic and energy publications). You do not see those documents. Do not use outside knowledge.

The input is a question and the answer's sentences, each with its index in square brackets.

Work in three steps (Claimify).

1. Selection. Read the answer sentence by sentence. Keep only content that states something checkable against a document: a value, a quantity, a date, a definition, a requirement, an event or a relation. Skip content that only restates the question, hedges, or describes the answer itself.
2. Disambiguation. If part of a sentence can be read in more than one way and the question and the answer together do not settle the reading, leave that part out rather than guess.
3. Decomposition. Split each selected sentence into atomic claims. Each claim states exactly one fact that is true or false on its own.

Rules for every claim:
- Decontextualise. The claim must be understandable with no other text. Replace pronouns and references ("it", "this account", "the table") with what they refer to, taken from the same sentence, another answer sentence or the question.
- Write the qualifiers inside the claim text: the entity (account, program, series, agency, bill, table or row), the unit, and the period (fiscal year, calendar year, quarter, estimate or actual) whenever the answer or the question states them.
- Copy every number exactly as the answer prints it, with its sign, commas, decimals, and any scale word or unit. Do not round, convert or compute, and do not add a number the answer does not contain.
- Add no fact that the answer does not state. The question may be used only to resolve a reference or to supply a qualifier; it is never the source of a new fact.
- Do not combine facts from two answer sentences in one claim. Do not repeat a claim.
- source_sentence_idx is the index of the answer sentence the claim comes from.
- qualifiers holds the entity, unit and period as written in the claim, each an empty string when neither the answer nor the question states it.

Return one JSON object that matches the required schema. If the answer states nothing checkable, return an empty claims list.
=== USER MESSAGE TEMPLATE ===
Question: {question}

Answer sentences:
{sentences}
