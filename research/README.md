# Research evaluations

Everything here is measurement code. It does not change what students see. Results and their dates are in
`docs/results/step-87-research-baselines.md` and `docs/results/step-88-research-strength.md`; raw outputs are in
`docs/results/data/step-8*.txt`.

## 1. Explanations: verified flow against plain and hint-only calls (needs the running stack)

Run inside the api container of a throwaway stack that holds the provider keys (never the live stack):

    docker exec <api-container> python -m evaluation.baselines --repeats 3 --strong groq:openai/gpt-oss-120b
    docker exec <api-container> python -m evaluation.explain_rate

Human rating sheet (G-5). The people who rate must not see the key:

    python -m evaluation.rating_sheet generate SHEET.csv KEY.csv --size 60 --hint
    python -m evaluation.rating_sheet compute SHEET.csv KEY.csv        # after two raters filled r1_* and r2_*

`--size N` takes the first N failing submissions from `evaluation/rating_sheet.py` and `evaluation/rating_more.py`;
`--hint` adds a hint-only explanation per submission. Rate 1 only if every claim is correct, otherwise 0.
`llm-rate` fills the reviewer columns with language models for a dry run; those rows are labelled as not human.

## 2. Placement: adaptive against random, fixed order and a max-information test (no stack needed)

    cd backend && python -m simulation.run --students 500 --seed 2026

The bank is read from `data/bank`. The students are synthetic; see the limits printed at the end of the report.

## 3. Mastery rule as a next-answer predictor (own virtual environment)

The scripts need numpy, pandas, scikit-learn, scipy and pyBKT. They are not part of the project's requirements; make a
separate environment:

    python -m venv kt-venv && kt-venv/Scripts/pip install numpy pandas scikit-learn scipy pyBKT

Datasets are not in the repository and must not be committed. Put them in a `Datasets` folder beside the repository, or
set `KT_DATA_DIR`:

    Datasets/ASSISTments2009/skill_builder_data.csv     corrected skill-builder file (346,860 rows)
    Datasets/EdNet/EdNet-KT1.zip  and  Datasets/EdNet/contents/questions.csv
    Datasets/CSEDM/Data/MainTable.csv                   (step 91 only; first run of each student on each problem)

EdNet is CC BY-NC 4.0 (attribution, non-commercial). Check each dataset's terms before sharing anything derived from it.

    cd research/kt_comparison
    python compare.py assist09 --folds 5 --fit --fit-skill            # models against each other
    python cold_start.py assist09 --folds 3                           # AUC and calibration against training size
    python calibration.py assist09 --folds 3                          # Platt and isotonic maps, pre-set success rule
    python significance.py assist09 --folds 5 --bkt --fit-skill       # student bootstrap, paired differences
    python cold_start_plus.py --folds 5 --bootstrap 100               # step 91: stack started from other datasets' weights
    python test_cold_start_plus.py                                    # checks of its core functions
    python baselines_plus.py --folds 5 --bootstrap 100                # step 92: PFA, Rasch, gradient boosting, hybrid
    python baselines_plus.py --targets ednet --ednet-seed 1           # replication on a second EdNet sample
    python baselines_plus.py --sequence                               # also sakt, sakt_item, akt_lite (needs PyTorch)
    python baselines_plus.py --published --save DIR                   # also the pyKT DKT and AKT (pip install --no-deps pykt-toolkit==0.0.38);
                                                                      # --save keeps each fold's test predictions
    python analyze_predictions.py DIR assist09                        # tables and intervals from the saved folds, also while a run is unfinished
    python baselines_plus.py --placebo --skip pfa,rasch               # leak check: labels permuted, every model should score about 0.5
    python baselines_plus.py --order-seed 1 --levels 30,100           # another random order of the training students
    python baselines_plus.py --targets assist09 --half 0              # run on a random half of the students
    python sensitivity_plus.py                                        # declared constants halved and doubled
    (the same with `ednet --students 1500` for EdNet)

`kt_comparison.ipynb` is a self-contained version for Kaggle: upload `skill_builder_data.csv` as a private dataset, add it
as input, switch the internet on once (to install pyBKT) and run all cells.

The sequence models need PyTorch, which has no wheel for Python 3.15: use a Python 3.12 environment
(`pip install torch --index-url https://download.pytorch.org/whl/cpu numpy pandas scikit-learn scipy`) for `--sequence`
and for `test_cold_start_plus.py`.

## Known issues

- pyBKT fails at import and in fitting with recent scikit-learn and numpy. The scripts include a small shim; the notebook
  patches one line of pyBKT's `fit/EM_fit.py` in the installed copy. The model itself is not changed.
- Fitting all skills in one `Model.fit` call gave AUC about 0.51; the scripts fit one model per skill.
- Fold assignment comes from scikit-learn and can differ between versions, so numbers move slightly between machines.
  Report the standard deviation, the date and the library versions with any table.
- pyBKT's own multiprocessing can use more than 1 GB of virtual memory per worker; the scripts run it in one process.
