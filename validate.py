import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

team_df = pd.read_csv("team_level_features.csv")
raw_df = pd.read_csv("match_prediction_features.csv")

FEATURES = ["elo_adv", "prev_xg_adv"]
X_raw = team_df[FEATURES].copy()
means, stds = X_raw.mean(), X_raw.std()
X = (X_raw - means) / stds
X.insert(0, "const", 1.0)
Xmat = X.values
y = team_df["win"].values
n, K = Xmat.shape

def neg_loglik(beta):
    z = Xmat @ beta
    return np.sum(np.logaddexp(0, z) - y * z)

res = minimize(neg_loglik, np.zeros(K), method="BFGS")
beta_hat = res.x

def predict_win_probability(team_elo, opponent_elo, team_prev_xg, opponent_prev_xg):
    elo_adv_std = (team_elo - opponent_elo - means["elo_adv"]) / stds["elo_adv"]
    xg_adv_std = (team_prev_xg - opponent_prev_xg - means["prev_xg_adv"]) / stds["prev_xg_adv"]
    logit = beta_hat[0] + beta_hat[1] * elo_adv_std + beta_hat[2] * xg_adv_std
    return 1 / (1 + np.exp(-logit))

out = raw_df[["match_id", "home_team_name", "away_team_name", "home_score", "away_score", "match_result"]].copy()

out["home_win_prob"] = out.apply(
    lambda r: predict_win_probability(
        team_elo=raw_df.loc[r.name, "home_elo"],
        opponent_elo=raw_df.loc[r.name, "away_elo"],
        team_prev_xg=raw_df.loc[r.name, "home_prev_avg_xg_scored"],
        opponent_prev_xg=raw_df.loc[r.name, "away_prev_avg_xg_scored"],
    ), axis=1
)
out["away_win_prob"] = out.apply(
    lambda r: predict_win_probability(
        team_elo=raw_df.loc[r.name, "away_elo"],
        opponent_elo=raw_df.loc[r.name, "home_elo"],
        team_prev_xg=raw_df.loc[r.name, "away_prev_avg_xg_scored"],
        opponent_prev_xg=raw_df.loc[r.name, "home_prev_avg_xg_scored"],
    ), axis=1
)

out["predicted_winner"] = np.where(out["home_win_prob"] > out["away_win_prob"],
                                    out["home_team_name"], out["away_team_name"])
out["actual_winner"] = np.select(
    [out["match_result"] == "H", out["match_result"] == "A"],
    [out["home_team_name"], out["away_team_name"]],
    default="Draw"
)
out["correct"] = (out["predicted_winner"] == out["actual_winner"])

out.to_csv("all_104_predictions.csv", index=False)

decisive = out[out["actual_winner"] != "Draw"]  
accuracy = decisive["correct"].mean()
n_draws = (out["actual_winner"] == "Draw").sum()

print(f"Total matches: {len(out)}  (includes {n_draws} draws, which this binary model can't call)")
print(f"Decisive matches (no draw): {len(decisive)}")
print(f"Correct winner picks: {decisive['correct'].sum()} / {len(decisive)} = {accuracy:.1%}\n")

print("Calibration (does '70% confidence' actually win ~70% of the time?):")
home_side = out[["home_win_prob"]].rename(columns={"home_win_prob": "prob"})
home_side["won"] = (out["match_result"] == "H").astype(int)
away_side = out[["away_win_prob"]].rename(columns={"away_win_prob": "prob"})
away_side["won"] = (out["match_result"] == "A").astype(int)
all_calls = pd.concat([home_side, away_side], ignore_index=True)

bins = [0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
labels = ["0-30%", "30-40%", "40-50%", "50-60%", "60-70%", "70-100%"]
all_calls["bucket"] = pd.cut(all_calls["prob"], bins=bins, labels=labels, include_lowest=True)
calib = all_calls.groupby("bucket", observed=True).agg(
    n=("won", "size"), predicted_avg=("prob", "mean"), actual_win_rate=("won", "mean")
).reset_index()
print(calib.to_string(index=False))

print("\nSample of predictions vs actual (first 15 matches):")
pd.set_option("display.width", 140)
print(out[["home_team_name", "away_team_name", "home_win_prob", "away_win_prob",
           "match_result", "predicted_winner", "actual_winner", "correct"]].head(15).to_string(index=False))
