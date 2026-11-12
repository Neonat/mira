# Hong Kong guest report with two Wolfsberg link citations

On 12 November 2026, the hosted QR was switched to revision `291353ea-179f-4e7c-89e4-5cd58de83419`. The revision keeps the [139-finding draft](2026-11-12-hk-sfc-footnote-followup.md) and its 407 exact passage citations intact. It adds two original paraphrases of industry guidance. The underlying draft retains its human-review-pending label.

| Benchmark item | Publication | Reviewed paraphrase |
|---|---|---|
| GT17 | [Risk-based approach, 23 June 2026](https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach) | Wolfsberg advises banks to direct resources toward their most significant financial-crime risks and scale back controls that contribute little. |
| GT19 | [Banking services for non-bank payment providers, 15 July 2026](https://wolfsberg-group.org/news/guidance-on-the-provision-of-banking-services) | Wolfsberg advises banks to adjust due diligence and monitoring to the risks of the payment services each provider actually offers. |

Codex checked each paraphrase against its publisher release. The operator approved adding the displayed paraphrases. Each frozen citation contains the source URL, release date, location description, original paraphrase and review record. The revision stored no Wolfsberg files or passages and included no quotations. Source permissions remained `metadata` and `fetch`. No Mira models or ingestion jobs ran.

The hosted transaction verified the original HTML hash, cloned the report and its exact finding and review bindings, and rehearsed anonymous generation and download. The downloaded HTML contained both paraphrases and both official links. The guest copy and test window were rolled back. The QR switch preserved the Australia and UAE pointers and the previous Hong Kong template.

The hosted receipt reported **139** original finding bindings and **409** citation rows including the two reviewed links. SHA-256 of the sorted citation URL rows joined by a newline was `0eb9be6556d191c867846e54fdf6af5acc5e44323091b03cd3a7001495b9238b`. It matched the exact URL set scored offline with the corrected [Hong Kong benchmark](../m0_ground_truth.csv) for 4 November 2025 through 4 November 2026. The result was **18/18 overall**, **18/18 fetchable** and **14/14 regulatory**. The hosted template HTML SHA-256 was `d3aadfe8586e14c567c1954d7bf625459a9537cd09535f5b1a681ae137f90527`. [Publication and verification transaction](../../scripts/publish_hk_wolfsberg_guest_revision.sql)
