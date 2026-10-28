"""Sequence knowledge-tracing baselines for the cold-start comparison (TR-V-05). Needs PyTorch (Python 3.12 environment).

  sakt        Self-Attentive Knowledge Tracing (Pandey and Karypis, 2019): exercise = skill; one attention block over the
              student's earlier (skill, correct) interactions
  sakt_item   the same with an item embedding added to the exercise and to the interaction (items seen fewer than twice
              in training share an "unknown" embedding)
  akt_lite    a simplified relative of AKT (Ghosh et al., 2020): Rasch-style question embeddings (skill embedding plus an
              item difficulty scalar times a skill variation vector) and attention scores with a learned monotonic decay
              over the distance to each earlier answer; ONE attention block, so it is not the published AKT

Training uses only the N training students; 20% of them (at least one) are held out to stop training early. Test students
are scored from their own earlier answers only (windows of 100 answers, each prediction has at least 50 earlier answers
when the student has that many). Constants are declared here and were not tuned on test students.
"""
import numpy as np
import pandas as pd
import torch
from torch import nn

WINDOW, STRIDE = 100, 50
DIM, HEADS, DROPOUT = 48, 2, 0.2
LEARNING_RATE, WEIGHT_DECAY, BATCH, MAX_EPOCHS, PATIENCE = 2e-3, 1e-5, 64, 40, 4
torch.set_num_threads(8)


class Net(nn.Module):
    def __init__(self, skills: int, items: int, kind: str):
        super().__init__()
        self.kind = kind
        self.use_item = kind in ("sakt_item", "akt_lite")
        self.skill_q = nn.Embedding(skills + 1, DIM)
        self.skill_kv = nn.Embedding(2 * (skills + 1), DIM)
        self.position = nn.Embedding(WINDOW, DIM)
        self.start = nn.Parameter(torch.zeros(1, 1, DIM))
        if kind == "sakt_item":
            self.item_q = nn.Embedding(items + 1, DIM)
            self.item_kv = nn.Embedding(2 * (items + 1), DIM)
        if kind == "akt_lite":
            self.difficulty = nn.Embedding(items + 1, 1)
            self.variation_q = nn.Embedding(skills + 1, DIM)
            self.variation_kv = nn.Embedding(2 * (skills + 1), DIM)
            nn.init.zeros_(self.difficulty.weight)
            self.decay = nn.Parameter(torch.full((HEADS,), -2.0))
        self.attention = nn.MultiheadAttention(DIM, HEADS, dropout=DROPOUT, batch_first=True)
        self.norm1, self.norm2 = nn.LayerNorm(DIM), nn.LayerNorm(DIM)
        self.feed = nn.Sequential(nn.Linear(DIM, DIM), nn.ReLU(), nn.Dropout(DROPOUT), nn.Linear(DIM, DIM))
        self.drop = nn.Dropout(DROPOUT)
        self.out = nn.Linear(DIM, 1)
        past = torch.arange(WINDOW)
        gap = (past[:, None] - past[None, :]).float()  # query position minus key position
        self.register_buffer("gap", gap)
        self.register_buffer("causal", gap <= 0)  # a key at or after the query is hidden

    def forward(self, skill, item, correct):
        q = self.skill_q(skill)
        kv = self.skill_kv(skill * 2 + correct)
        if self.kind == "sakt_item":
            q = q + self.item_q(item)
            kv = kv + self.item_kv(item * 2 + correct)
        if self.kind == "akt_lite":
            mu = self.difficulty(item)
            q = q + mu * self.variation_q(skill)
            kv = kv + mu * self.variation_kv(skill * 2 + correct)
        batch, length = skill.shape
        keys = kv + self.position(torch.arange(length, device=skill.device))
        keys = torch.cat([self.start.expand(batch, 1, DIM), keys], dim=1)  # a start token so no query has an empty history
        hidden = self.causal[:length, :length]
        bias = torch.zeros(HEADS, length, length + 1, device=skill.device)
        if self.kind == "akt_lite":
            bias[:, :, 1:] = -nn.functional.softplus(self.decay)[:, None, None] * self.gap[:length, :length].clamp(min=0)
        bias[:, :, 1:] = bias[:, :, 1:].masked_fill(hidden[None], float("-inf"))
        mask = bias[None].expand(batch, -1, -1, -1).reshape(batch * HEADS, length, length + 1)
        attended, _ = self.attention(q, keys, keys, attn_mask=mask, need_weights=False)
        h = self.norm1(q + self.drop(attended))
        h = self.norm2(h + self.drop(self.feed(h)))
        return self.out(h).squeeze(-1)


def windows(frame: pd.DataFrame, skills: dict, items: dict, training: bool):
    """Padded windows of one student's answers: skill, item, correct, valid, scored (rows to count), original row."""
    skill_ids = frame["skill_name"].map(skills).fillna(0).astype(int).to_numpy()
    item_ids = frame["item_id"].map(items).fillna(0).astype(int).to_numpy()
    correct = frame["correct"].to_numpy().astype(int)
    users = frame["user_id"].to_numpy()
    rows_by_user = pd.Series(np.arange(len(frame))).groupby(users).indices
    out = {k: [] for k in ("skill", "item", "correct", "valid", "scored", "row")}
    for rows in rows_by_user.values():
        length, covered, start = len(rows), 0, 0
        while covered < length:
            end = min(start + WINDOW, length)
            take = rows[start:end]
            pad = WINDOW - len(take)
            first_scored = 0 if training else covered - start
            scored = np.zeros(WINDOW, bool)
            scored[first_scored:len(take)] = True
            for key, values in (("skill", skill_ids), ("item", item_ids), ("correct", correct)):
                out[key].append(np.concatenate([values[take], np.zeros(pad, int)]))
            out["valid"].append(np.concatenate([np.ones(len(take), bool), np.zeros(pad, bool)]))
            out["scored"].append(scored)
            out["row"].append(np.concatenate([take, np.full(pad, -1)]))
            covered = end
            start += WINDOW if training else STRIDE
    if not out["skill"]:
        return {k: torch.zeros((0, WINDOW), dtype=torch.bool if k in ("valid", "scored") else torch.long) for k in out}
    return {k: torch.as_tensor(np.stack(v)) for k, v in out.items()}


def sequence_predict(sub: pd.DataFrame, test: pd.DataFrame, kind: str, seed: int = 0) -> np.ndarray:
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
    net = Net(len(skills), len(items), kind)
    optimiser = torch.optim.Adam(net.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")

    def forward(w):
        return net(w["skill"], w["item"], w["correct"])

    def validation_loss() -> float:
        net.eval()
        with torch.no_grad():
            z = forward(valid_w)
            m = valid_w["scored"]
            return float(loss_fn(z, valid_w["correct"].float())[m].mean())

    best, best_state, wait = np.inf, None, 0
    for _ in range(MAX_EPOCHS):
        net.train()
        order = torch.randperm(len(train_w["skill"]))
        for i in range(0, len(order), BATCH):
            b = order[i:i + BATCH]
            batch = {k: v[b] for k, v in train_w.items()}
            z = forward(batch)
            loss = loss_fn(z, batch["correct"].float())[batch["valid"]].mean()
            optimiser.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            optimiser.step()
        current = validation_loss() if len(valid_w["skill"]) else best - 1
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
    out = np.full(len(test), 0.5)
    with torch.no_grad():
        for i in range(0, len(test_w["skill"]), 256):
            batch = {k: v[i:i + 256] for k, v in test_w.items()}
            p = torch.sigmoid(forward(batch))
            m = batch["scored"]
            out[batch["row"][m].numpy()] = p[m].numpy()
    return out
