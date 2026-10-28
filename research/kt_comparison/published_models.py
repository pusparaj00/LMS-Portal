"""Published DKT and AKT, from the pyKT reference implementations, in the cold-start protocol (TR-V-05). Needs PyTorch.

  dkt   Deep Knowledge Tracing (Piech et al., 2015): pyKT `dkt.py`, an LSTM over (skill, correct) interactions
  akt   Context-aware Attentive Knowledge Tracing (Ghosh et al., 2020): pyKT `akt.py`, Rasch embeddings with item
        difficulty, monotonic attention with learned decay, a knowledge retriever that cannot see the current response

The model classes are pyKT's (pykt-toolkit 0.0.38, MIT), loaded from the installed files by path because the package
`__init__` imports data-preparation code we do not use. The training loop, windows, folds, early stopping and scoring are
ours and the same as for sequence_models.py, so that the models see the same N students and score the same test rows.
DKT has no prediction for a student's first answer; those rows get the training mean. Sizes and constants are declared here
and were not tuned on test students: d = 128, dropout 0.1 (DKT) and 0.2 (AKT), AKT with 2 blocks, 8 heads, feed-forward 256,
final layer 512, L2 1e-5 on item difficulties.
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd
import torch
from sequence_models import WINDOW, windows
from torch import nn

DIM = 128
LEARNING_RATE, BATCH, MAX_EPOCHS, PATIENCE = 1e-3, 64, 30, 4
torch.set_num_threads(int(os.environ.get("KT_THREADS", "8")))


def _load(name: str):
    site = next(p for p in sys.path if p.endswith("site-packages"))
    path = os.path.join(site, "pykt", "models", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"pykt_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(kind: str, skills: int, items: int) -> nn.Module:
    if kind == "dkt":
        return _load("dkt").DKT(num_c=skills + 1, emb_size=DIM, dropout=0.1)
    return _load("akt").AKT(n_question=skills + 1, n_pid=items, d_model=DIM, n_blocks=2, dropout=0.2, d_ff=256,
                            kq_same=1, final_fc_dim=512, num_attn_heads=8, l2=1e-5)


def probabilities(net: nn.Module, kind: str, w: dict) -> tuple[torch.Tensor, torch.Tensor]:
    """P(correct) for every position, and which positions have a prediction (all for AKT, all but the first for DKT)."""
    skill, correct = w["skill"], w["correct"]
    if kind == "akt":
        p, penalty = net(skill, correct, w["item"])
        return p, penalty
    y = net(skill, correct)
    follows = y[:, :-1].gather(2, skill[:, 1:, None]).squeeze(-1)
    p = torch.cat([torch.full_like(follows[:, :1], float("nan")), follows], dim=1)
    return p, torch.zeros(())


def published_predict(sub: pd.DataFrame, test: pd.DataFrame, kind: str, seed: int = 0) -> np.ndarray:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    skills = {s: i + 1 for i, s in enumerate(sub["skill_name"].unique())}
    counts = sub["item_id"].value_counts()
    items = {s: i + 1 for i, s in enumerate(counts[counts >= 2].index)}
    users = sub["user_id"].unique()
    held = set(rng.choice(users, size=max(1, len(users) // 5), replace=False))
    is_held = sub["user_id"].isin(held).to_numpy()
    train_w = windows(sub[~is_held].reset_index(drop=True), skills, items, training=True)
    valid_w = windows(sub[is_held].reset_index(drop=True), skills, items, training=False)
    net = build(kind, len(skills), len(items))
    optimiser = torch.optim.Adam(net.parameters(), lr=LEARNING_RATE)

    def loss_of(w, mask):
        p, penalty = probabilities(net, kind, w)
        keep = mask & ~torch.isnan(p)
        p = torch.nan_to_num(p, nan=0.5).clamp(1e-6, 1 - 1e-6)
        target = w["correct"].float()
        bce = -(target * p.log() + (1 - target) * (1 - p).log())
        return (bce * keep).sum() / keep.sum().clamp(min=1) + penalty

    best, best_state, wait = np.inf, None, 0
    for _ in range(MAX_EPOCHS):
        net.train()
        order = torch.randperm(len(train_w["skill"]))
        for i in range(0, len(order), BATCH):
            batch = {k: v[order[i:i + BATCH]] for k, v in train_w.items()}
            loss = loss_of(batch, batch["valid"])
            optimiser.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            optimiser.step()
        net.eval()
        with torch.no_grad():
            current = float(loss_of(valid_w, valid_w["scored"])) if len(valid_w["skill"]) else best - 1
        if current < best - 1e-4:
            best, best_state, wait = current, {k: v.clone() for k, v in net.state_dict().items()}, 0
        else:
            wait += 1
            if wait >= PATIENCE:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.eval()
    test_w = windows(test, skills, items, training=False)
    out = np.full(len(test), float(sub["correct"].mean()))
    with torch.no_grad():
        for i in range(0, len(test_w["skill"]), 128):
            batch = {k: v[i:i + 128] for k, v in test_w.items()}
            p, _ = probabilities(net, kind, batch)
            keep = batch["scored"] & ~torch.isnan(p)
            out[batch["row"][keep].numpy()] = p[keep].numpy()
    return out
