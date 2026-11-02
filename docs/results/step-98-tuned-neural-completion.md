# Step 98: tuned DKT and AKT completed on EdNet and CSEDM (TR-V-05)

Date: 2026-11-02. Completes the item "Not done" in [step-95](step-95-paper-controls.md) section 8. Raw output: `docs/results/data/step-98-tuned-neural-ednet.txt`
and `step-98-tuned-neural-csedm.txt`. Started 12:16, finished about 13:10 local time (about 55 minutes, two processes in parallel).

    python research/kt_comparison/baselines_plus.py --targets ednet --published --neural-tuned dkt,akt --skip pfa,rasch --folds 5 --bootstrap 100 --levels 30,100
    python research/kt_comparison/baselines_plus.py --targets csedm  --published --neural-tuned dkt,akt --skip pfa,rasch --folds 5 --bootstrap 100 --levels 30,100

Same declared budget as step 94: six (learning rate, width, dropout) settings, chosen by log loss on a held-out fifth of the N training students; test
students are not used to choose. EdNet is sample 1 (1,500 students). Mean AUC over five folds:

| Dataset | N | DKT | DKT tuned | AKT | AKT tuned | Stack |
| --- | --- | --- | --- | --- | --- | --- |
| ASSISTments (step 94) | 30 | 0.5904 | 0.6037 | 0.6483 | 0.6786 | 0.7101 |
| ASSISTments (step 94) | 100 | 0.6403 | 0.6425 | 0.7094 | 0.7085 | 0.7227 |
| EdNet 1 | 30 | 0.5382 | 0.5393 | 0.5748 | 0.5773 | 0.6556 |
| EdNet 1 | 100 | 0.5695 | 0.5792 | 0.6179 | 0.6188 | 0.6683 |
| CSEDM | 30 | 0.7736 | 0.7721 | 0.7621 | 0.7607 | 0.7843 |
| CSEDM | 100 | 0.7856 | 0.7845 | 0.7764 | 0.7779 | 0.7982 |

- **All 12 tuned figures are below the stack's mean AUC.** The smallest gap is tuned DKT on CSEDM at N = 30 (0.7721 against 0.7843).
- Tuned minus untuned changes AUC by at most 0.002 (up or down) in 7 of the 12 cells; the largest gain is AKT on ASSISTments at N = 30 (+0.0303), and
  tuning lowered the mean in 4 cells, each by 0.0015 or less (CSEDM DKT and AKT, ASSISTments AKT at N = 100).
- Intervals from the same runs (stack minus untuned DKT and AKT, 100 resamples): CSEDM N = 30 DKT +0.0107 (+0.0061 to +0.0152), AKT +0.0281;
  N = 100 DKT +0.0129, AKT +0.0261; EdNet N = 30 DKT +0.1301, AKT +0.0967. No interval was computed against the tuned models.
- Stack against gradient boosting on CSEDM at N = 100 is +0.0020 (0.0000 to +0.0051), the tie reported in the paper.

## Limits

Six settings is a small search; stronger tuning could narrow the gaps, as the paper says. No pretrained or fine-tuned comparators, one EdNet sample, no
neural-model seeds. The `lms_default` and stack columns repeat the numbers of steps 92 and 95 for the same folds (EdNet 0.6556 and 0.6683,
CSEDM 0.7843 and 0.7982).

## Paper

`Research_Paper_Audited` and `Research_Paper_ICALT_5page` (outside the repository) now report the twelve tuned figures instead of "complete only for
ASSISTments" and were re-rendered in Word (12 and 5 pages).
