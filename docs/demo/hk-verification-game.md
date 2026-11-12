# Review the Finding

The player is the compliance reviewer at a fictional Hong Kong bank. Each of three cases presents one draft finding, its review cutoff and an HKMA excerpt. The player approves, sends back or escalates. **Undo** reopens the most recent decision, including from the results screen. The debrief explains the recommended training decision and shows the corresponding Mira verification evidence.

The public practice game runs entirely in the browser on GitHub Pages. [Play Review the Finding](https://neonat.github.io/mira-smu-ytp-aif-2026/)

**Copy summary** copies the score, the player's decision and the suggested decision for each answered case, and the reason behind the guidance. The summary is intended for a coaching discussion with a compliance lead. **Skip to end** opens labelled sample results before play and previews the player's results once they have answered. **Back to game** resumes the current case with its progress intact.

On skipping, two matches on the first two cases trigger confetti and a link to the public findings. Two misses show a brief sad face followed by a prompt to revisit the case explanations. The original hosted rehearsal linked to a signed-in Hong Kong review queue, where reviewers and admins could save evidence decisions on the selected workspace’s latest prepared report.

| Case | Recommended action | Verification link |
|---|---|---|
| Sanctions screening testing schedule | Approve | Replay the saved supported verdict on the original frozen finding and evidence. |
| Guidance update | Send back | Run Mira’s publication cutoff check on the same source with a training cutoff one day earlier. The source is too late for that brief. |
| Information-sharing controls | Escalate | Replay the original partially supported verdict. The cited list lacks the introductory language needed to establish the obligation. |

The builder reads the pinned local verification records in a repeatable-read transaction. It checks each stored input fingerprint, confirms the HKMA source can still be quoted, and applies the same quotation and date guards as the factual verifier. Support verdicts are historical records tied to the exact original inputs. The earlier-cutoff exercise stops at the date gate. The three recommended player actions are training decisions.

Use missed decisions to identify coaching topics. If reviewer readiness later becomes part of the workflow, assess it on unseen cases and have a compliance lead authorize sign-off. Live findings still require their own evidence checks and authorized review.

Set `MIRA_TEST_DATABASE_URL` to the loopback database that contains the saved Hong Kong checks and run from the repository root.

```sh
python -m eval.hk_verification_game
```

Open `reports/hk-verification-game/index.html` in a browser. The generated game includes short saved excerpts and stays in the ignored local reports directory. Play is self-contained. Player decisions live in the current browser session and have no write path into research or sign-off.
