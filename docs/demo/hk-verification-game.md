# Review the Finding

The player is the compliance reviewer at a fictional Hong Kong bank. Each of three cases presents one draft finding, its review cutoff and an HKMA excerpt. The player approves, sends back or escalates. The debrief explains the recommended training decision and shows the corresponding Mira verification evidence.

| Case | Recommended action | Verification link |
|---|---|---|
| Sanctions screening testing schedule | Approve | Replay the saved supported verdict on the original frozen finding and evidence. |
| Guidance update | Send back | Run Mira’s publication cutoff check on the same source with a training cutoff one day earlier. The source is too late for that brief. |
| Information-sharing controls | Escalate | Replay the original partially supported verdict. The cited list lacks the introductory language needed to establish the obligation. |

The builder reads the pinned local verification records in a repeatable-read transaction. It checks each stored input fingerprint, confirms the HKMA source can still be quoted, and applies the same quotation and date guards as the factual verifier. Support verdicts are historical records tied to the exact original inputs. The earlier-cutoff exercise stops at the date gate. The three recommended player actions are training decisions.

Set `MIRA_TEST_DATABASE_URL` to the loopback database that contains the saved Hong Kong checks and run from the repository root.

```sh
python -m eval.hk_verification_game
```

Open `reports/hk-verification-game/index.html` in a browser. The generated game includes short saved excerpts and stays in the ignored local reports directory. Play is self-contained. Player decisions live in the current browser session and have no write path into research or sign-off.
