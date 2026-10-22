# Discovery and distribution

Repository name remains `postgrad-study-engine`. This work changes public
presentation only; runtime, evidence contracts, private Vaults and version locks
are not upgraded. Do not republish an existing release/tag for a documentation
change.

## Desired repository settings

[repository-profile.json](repository-profile.json) records the exact public
About description, 18 Topics and homepage target. It is an editorial target,
not a GitHub synchronization file. Actual settings must be saved through an
admin-capable surface and read back from GitHub before claiming completion.
The FSRS wording is explicitly optional: the engine includes an adapter, while
its default scheduler remains rule-based and optimized FSRS training scores are
not held-out human validation.

Topics follow GitHub's lowercase/numbers/hyphens rule, <=50 characters each and
<=20 topics. `obsidian` denotes plain Markdown compatibility, not a dedicated
plugin. `knowledge-tracing` denotes learning-state tracking, not an implemented
BKT/DKT model or validated cognitive diagnosis. No unrelated agent/RAG/MCP
capability is claimed.

Set Social preview to [the selected public JPEG](../assets/social-preview.jpg).
The image is 1774 × 887, 245,482 bytes, with a dark background, paper archives
and the title “考研 AI 私教”. Uploading it in repository Settings is a separate
step from committing the file. Recheck the resulting preview before reporting
it configured.

## Search facts and baseline

GitHub's [repository-search documentation](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)
says the default name/description/topic search does not include README unless
`in:readme` is requested. Its public documentation does not establish a fixed
ranking-weight order among these fields. A matching topic improves eligibility
for topic searches; it does not guarantee a numerical rank.

[The pre-change snapshot](search-baseline-2026-10-22.json) records the three
visible target queries, first page and returned names. The project was absent
from the returned first 20 for each. That is a bounded observation, not an exact
global rank or evidence for a claimed total result count.

For a later comparable check, use repository search, the same query text,
default relevance, page 1 and 20 results. Record date/time, surface and returned
names. Separately test `topic:fsrs`, `topic:kaoyan` and `in:readme` to distinguish
metadata matching from text matching. Google and GitHub are separate indexes;
do not merge their results or promise an indexing deadline.

| Query | Aspirational first-stage target | Pre-change observation |
| --- | --- | --- |
| `FSRS learning engine` | First 10 | Absent from returned first 20 |
| `evidence-based learning engine` | First 10 | Absent from returned first 20 |
| `kaoyan AI` | First 20 | Absent from returned first 20 |

These targets are experiments, not delivery guarantees. Retest after actual
metadata changes have had time to index; a README-only merge is not a substitute
for writing the missing metadata.

## External distribution drafts

- [Weekly self-recommendation](weekly-self-recommendation.md): addressed to
  `ruanyf/weekly`, whose README accepts software/article/resource submissions.
- [Two Awesome-list suggestions](awesome-submissions.md): optional FSRS
  application and education Open Source/Watchlist layers, with affiliation and
  evidence limits disclosed. The research-paper catalog was excluded as a poor
  fit for a software-only submission.
- [Chinese article draft](kaoyan-ai-memory-curve-article.md): a software replay
  with fictional observations, not a claimed personal or population outcome.

These files are drafts. They do not prove that any issue, PR, blog or social post
has been sent or accepted. Check current destination rules and duplication
before authorized submission. Inclusion is the destination maintainer's choice.
