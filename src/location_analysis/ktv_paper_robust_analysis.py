#!/usr/bin/env python3
"""
Paper-style robust analysis for KTV dataset.

Key design:
1) Spatial uncertainty sensitivity by geocoding confidence threshold.
2) Robust regression with HC3 SE.
3) Split package variable into official vs inferred.
4) Missing-data handling for avg_price via missing-indicator model.
"""

import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_cache")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import norm


DEFAULT_SHOPS = "data/processed/dianping_ktv_shop_profile_beijing_20260218_enriched_offline_s0.csv"
DEFAULT_REVIEWS = "data/raw/dianping_ktv_reviews_beijing_recent100_20260213.csv"
DEFAULT_OUT_DIR = "data/processed/ktv_analysis_20260218"

CORE_DISTRICTS = {"东城区", "西城区", "朝阳区", "海淀区", "丰台区"}

POS_WORDS = ["好", "不错", "满意", "推荐", "干净", "舒服", "热情", "划算", "超值", "方便", "喜欢", "赞"]
NEG_WORDS = ["差", "一般", "脏", "吵", "贵", "失望", "不好", "糟糕", "慢", "坑", "不推荐", "态度差"]


@dataclass
class OutPaths:
    base: Path
    fig: Path
    tables: Path


def ensure_dirs(out_dir: str) -> OutPaths:
    base = Path(out_dir)
    fig = base / "figures"
    tables = base / "tables"
    fig.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    return OutPaths(base=base, fig=fig, tables=tables)


def parse_amap_score(tags: str) -> float:
    if not isinstance(tags, str) or not tags.strip():
        return np.nan
    try:
        obj = json.loads(tags)
        return float(obj.get("amap_best_score"))
    except Exception:
        return np.nan


def parse_packages(packages: str) -> Tuple[int, int]:
    official = 0
    inferred = 0
    if not isinstance(packages, str) or not packages.strip():
        return official, inferred
    try:
        arr = json.loads(packages)
    except Exception:
        return official, inferred
    if not isinstance(arr, list):
        return official, inferred
    for x in arr:
        if not isinstance(x, dict):
            continue
        if x.get("deal_id"):
            official += 1
        if x.get("source") == "review_text":
            inferred += 1
    return official, inferred


def sentiment_label(score_avg: float, text: str) -> int:
    if not math.isnan(score_avg):
        if score_avg >= 4.0:
            return 1
        if score_avg >= 3.0:
            return 0
        return -1
    if not isinstance(text, str):
        return 0
    pos = sum(text.count(w) for w in POS_WORDS)
    neg = sum(text.count(w) for w in NEG_WORDS)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def load_data(shops_path: str, reviews_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    shops = pd.read_csv(shops_path, encoding="utf-8-sig")
    reviews = pd.read_csv(reviews_path, encoding="utf-8-sig")

    for c in ["lng", "lat", "rating", "review_count", "avg_price"]:
        shops[c] = pd.to_numeric(shops[c], errors="coerce")

    shops["amap_score"] = shops["tags"].fillna("").map(parse_amap_score)
    pkg = shops["packages"].fillna("").map(parse_packages)
    shops["pkg_official"] = [x[0] for x in pkg]
    shops["pkg_inferred"] = [x[1] for x in pkg]
    shops["pkg_total"] = shops["pkg_official"] + shops["pkg_inferred"]

    reviews["score_avg_num"] = pd.to_numeric(reviews["score_avg"], errors="coerce")
    reviews["sentiment"] = [
        sentiment_label(float(s) if pd.notna(s) else math.nan, t)
        for s, t in zip(reviews["score_avg_num"], reviews["content"])
    ]

    shop_review_rows = reviews.groupby("shop_id").size().rename("review_rows_from_reviews")
    shops = shops.merge(shop_review_rows, on="shop_id", how="left")
    shops["review_rows_from_reviews"] = shops["review_rows_from_reviews"].fillna(0).astype(int)
    shops["review_count_filled"] = shops["review_count"].copy()
    m = shops["review_count_filled"].isna()
    shops.loc[m, "review_count_filled"] = shops.loc[m, "review_rows_from_reviews"]
    shops["review_count_filled"] = shops["review_count_filled"].fillna(0)

    shops = shops[
        shops["lng"].between(115.0, 118.5, inclusive="both")
        & shops["lat"].between(39.0, 41.5, inclusive="both")
    ].copy()
    return shops, reviews


def moran_i_with_perm(values: np.ndarray, coords: np.ndarray, k: int = 8, n_perm: int = 199, seed: int = 2026) -> Tuple[float, float]:
    n = len(values)
    if n <= 12:
        return np.nan, np.nan
    k = min(k, n - 1)
    if k < 1:
        return np.nan, np.nan
    tree = cKDTree(coords)
    _, idx = tree.query(coords, k=k + 1)
    nbr = idx[:, 1:]

    z = values - values.mean()
    z = z / (z.std(ddof=0) + 1e-12)

    lag = z[nbr].mean(axis=1)
    i_obs = float(np.sum(z * lag) / np.sum(z * z))

    rng = np.random.default_rng(seed)
    sims = []
    for _ in range(n_perm):
        zp = rng.permutation(z)
        lagp = zp[nbr].mean(axis=1)
        sims.append(float(np.sum(zp * lagp) / np.sum(zp * zp)))
    sims = np.asarray(sims)
    p = float((np.sum(np.abs(sims) >= abs(i_obs)) + 1) / (n_perm + 1))
    return i_obs, p


def build_spatial_sensitivity(shops: pd.DataFrame, thresholds: List[float]) -> pd.DataFrame:
    rows: List[Dict[str, float]] = []
    for th in thresholds:
        sub = shops[shops["amap_score"] >= th].copy()
        n = len(sub)
        if n == 0:
            rows.append(
                {
                    "threshold": th,
                    "n_shops": 0,
                    "core_n": 0,
                    "noncore_n": 0,
                    "core_avg_log_reviews": np.nan,
                    "noncore_avg_log_reviews": np.nan,
                    "core_noncore_gap": np.nan,
                    "moran_i": np.nan,
                    "moran_p_perm": np.nan,
                }
            )
            continue
        sub["log_reviews"] = np.log1p(sub["review_count_filled"].astype(float))
        sub["is_core"] = sub["district"].isin(CORE_DISTRICTS)
        core = sub[sub["is_core"]]
        noncore = sub[~sub["is_core"]]
        core_avg = float(core["log_reviews"].mean()) if len(core) else np.nan
        noncore_avg = float(noncore["log_reviews"].mean()) if len(noncore) else np.nan
        gap = core_avg - noncore_avg if pd.notna(core_avg) and pd.notna(noncore_avg) else np.nan

        moran_i, moran_p = moran_i_with_perm(
            values=sub["log_reviews"].to_numpy(),
            coords=sub[["lng", "lat"]].to_numpy(),
            k=8,
            n_perm=199,
            seed=2026,
        )
        rows.append(
            {
                "threshold": th,
                "n_shops": int(n),
                "core_n": int(len(core)),
                "noncore_n": int(len(noncore)),
                "core_avg_log_reviews": core_avg,
                "noncore_avg_log_reviews": noncore_avg,
                "core_noncore_gap": gap,
                "moran_i": moran_i,
                "moran_p_perm": moran_p,
            }
        )
    return pd.DataFrame(rows)


def fit_ols_hc3(df: pd.DataFrame, y_col: str, x_cols: List[str]) -> pd.DataFrame:
    d = df[[y_col] + x_cols].copy()
    d = d.replace([np.inf, -np.inf], np.nan).dropna()
    y = d[y_col].to_numpy(dtype=float)
    X = d[x_cols].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(X)), X])
    names = ["Intercept"] + x_cols

    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    yhat = X @ beta
    resid = y - yhat
    h = np.sum(X * (X @ xtx_inv), axis=1)
    h = np.clip(h, 0.0, 0.999999)
    w = (resid / (1.0 - h)) ** 2
    meat = np.zeros((X.shape[1], X.shape[1]), dtype=float)
    for i in range(len(X)):
        xi = X[i : i + 1].T
        meat += w[i] * (xi @ xi.T)
    cov = xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.diag(cov))
    z = beta / (se + 1e-12)
    p = 2.0 * (1.0 - norm.cdf(np.abs(z)))
    ci_low = beta - 1.96 * se
    ci_high = beta + 1.96 * se

    out = pd.DataFrame(
        {
            "term": names,
            "coef": beta,
            "se_hc3": se,
            "z": z,
            "p_value": p,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_obs": len(d),
        }
    )
    return out


def build_regression_panel(shops: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    sent = (
        reviews.groupby("shop_id")
        .agg(
            pos_rate=("sentiment", lambda s: float((s == 1).mean())),
            sent_n=("sentiment", "size"),
        )
        .reset_index()
    )
    df = shops.merge(sent, on="shop_id", how="left")
    df["pos_rate"] = df["pos_rate"].fillna(df["pos_rate"].mean())
    df["is_core"] = df["district"].isin(CORE_DISTRICTS).astype(int)
    df["y"] = np.log1p(df["review_count_filled"].astype(float))
    df["rating_f"] = df["rating"].fillna(df["rating"].median())
    df["avg_price_missing"] = df["avg_price"].isna().astype(int)
    df["avg_price_f"] = df["avg_price"].fillna(df["avg_price"].median())
    return df


def plot_sensitivity(sens: pd.DataFrame, fig_dir: Path) -> None:
    plt.figure(figsize=(8, 5))
    plt.plot(sens["threshold"], sens["moran_i"], marker="o", linewidth=2)
    for _, r in sens.iterrows():
        plt.text(r["threshold"], r["moran_i"], f"n={int(r['n_shops'])}", fontsize=8, ha="center", va="bottom")
    plt.xlabel("Amap Match Score Threshold")
    plt.ylabel("Moran's I")
    plt.title("Spatial Autocorrelation Sensitivity")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(fig_dir / "14_moran_threshold_sensitivity.png", bbox_inches="tight", dpi=160)
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(sens["threshold"], sens["core_noncore_gap"], marker="o", linewidth=2, color="#F58518")
    for _, r in sens.iterrows():
        if pd.notna(r["core_noncore_gap"]):
            plt.text(r["threshold"], r["core_noncore_gap"], f"{r['core_noncore_gap']:.2f}", fontsize=8, ha="center", va="bottom")
    plt.xlabel("Amap Match Score Threshold")
    plt.ylabel("Core - NonCore Avg log(1+reviews)")
    plt.title("Core/Non-Core Gap Sensitivity")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(fig_dir / "15_core_gap_threshold_sensitivity.png", bbox_inches="tight", dpi=160)
    plt.close()


def write_method_doc(out: OutPaths) -> None:
    text = """# 评论处理与稳健分析方法说明

## 评论处理
1. 评论去重键：`shop_id|review_id`。
2. 每店目标抓取最近100条，累计数据为增量合并。
3. 情感标注优先使用评分：`score_avg>=4` 判为正向，`3<=score_avg<4` 中性，`<3` 负向。
4. 当评论缺评分时，采用小型词典法（正/负词计数）作为回退。
5. LDA主题：中文分词后进行 LDA 主题建模，输出主题-情感矩阵。

## 论文口径稳健处理
1. 地理匹配不确定性：按 `amap_best_score` 阈值进行敏感性分析（0.0/0.4/0.5/0.6/0.75/0.82/0.9）。
2. 空间统计：每个阈值重算 Moran's I（含置换检验 p 值）。
3. 回归变量拆分：`pkg_official` 与 `pkg_inferred` 分开建模，避免混合解释。
4. 缺失处理：`avg_price` 采用“缺失指示变量 + 中位数填补”作为稳健模型。
5. 回归标准误：使用 HC3 异方差稳健标准误。
"""
    (out.base / "评论处理与稳健分析方法说明.md").write_text(text, encoding="utf-8")


def write_nonreview_retry_doc(out: OutPaths) -> None:
    text = """# 非评论字段补抓重试记录（2026-02-18）

目标：补抓地址/区县/官方套餐等“非评论字段”。

## 重试结果
1. 搜索页元信息链路（`https://www.dianping.com/search/keyword/2/0_KTV`）  
   结果：`net::ERR_TUNNEL_CONNECTION_FAILED`，未获取可用元数据。
2. 店铺详情API链路（`mapi/fun/shopdetailktvbooktable2.json2`）  
   结果：抽样50家均 `http_403`。
3. review-list 触发 `outsideshopreviewlist` 链路  
   结果：抽样20家均 `no_shopreview_resp`。

结论：本轮网络风控环境下，非评论字段的线上补抓通道不可用；因此地址/区县与套餐信息仍以现有离线融合结果为主。
"""
    (out.base / "非评论字段补抓重试记录_20260218.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-style robust analysis for KTV dataset.")
    parser.add_argument("--shops", default=DEFAULT_SHOPS)
    parser.add_argument("--reviews", default=DEFAULT_REVIEWS)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--main-threshold", type=float, default=0.75)
    args = parser.parse_args()

    out = ensure_dirs(args.out_dir)
    shops, reviews = load_data(args.shops, args.reviews)

    # Data quality summary.
    dq = pd.DataFrame(
        [
            {"metric": "n_shops", "value": int(len(shops))},
            {"metric": "n_reviews", "value": int(len(reviews))},
            {"metric": "address_nonempty", "value": int(shops["address"].fillna("").astype(str).str.strip().ne("").sum())},
            {"metric": "amap_score_nonnull", "value": int(shops["amap_score"].notna().sum())},
            {"metric": "amap_score_ge_0.75", "value": int((shops["amap_score"] >= 0.75).sum())},
            {"metric": "pkg_official_nonzero", "value": int((shops["pkg_official"] > 0).sum())},
            {"metric": "pkg_inferred_nonzero", "value": int((shops["pkg_inferred"] > 0).sum())},
            {"metric": "avg_price_nonnull", "value": int(shops["avg_price"].notna().sum())},
        ]
    )
    dq.to_csv(out.tables / "paper_data_quality_summary.csv", index=False, encoding="utf-8-sig")

    # Spatial sensitivity.
    thresholds = [0.0, 0.4, 0.5, 0.6, 0.75, 0.82, 0.9]
    sens = build_spatial_sensitivity(shops, thresholds)
    sens.to_csv(out.tables / "paper_spatial_threshold_sensitivity.csv", index=False, encoding="utf-8-sig")
    plot_sensitivity(sens, out.fig)

    # Regression robustness.
    reg_df = build_regression_panel(shops, reviews)
    model_rows: List[pd.DataFrame] = []

    # M1: main model on high-confidence geocoding sample.
    m1_df = reg_df[reg_df["amap_score"] >= args.main_threshold].copy()
    m1 = fit_ols_hc3(
        m1_df,
        y_col="y",
        x_cols=["rating_f", "pkg_official", "pkg_inferred", "pos_rate", "is_core"],
    )
    m1["model"] = f"M1_main_th{args.main_threshold:.2f}"
    model_rows.append(m1)

    # M2: missing-indicator model on same sample.
    m2 = fit_ols_hc3(
        m1_df,
        y_col="y",
        x_cols=["rating_f", "pkg_official", "pkg_inferred", "pos_rate", "is_core", "avg_price_f", "avg_price_missing"],
    )
    m2["model"] = f"M2_missingIndicator_th{args.main_threshold:.2f}"
    model_rows.append(m2)

    # M3: full sample reference model.
    m3 = fit_ols_hc3(
        reg_df,
        y_col="y",
        x_cols=["rating_f", "pkg_official", "pkg_inferred", "pos_rate", "is_core"],
    )
    m3["model"] = "M3_full_sample"
    model_rows.append(m3)

    reg_all = pd.concat(model_rows, ignore_index=True)
    reg_all = reg_all[
        ["model", "term", "coef", "se_hc3", "z", "p_value", "ci_low", "ci_high", "n_obs"]
    ]
    reg_all.to_csv(out.tables / "paper_regression_robust_models.csv", index=False, encoding="utf-8-sig")

    write_method_doc(out)
    write_nonreview_retry_doc(out)

    print(f"done robust tables={out.tables}")
    print(f"done robust figures={out.fig}")


if __name__ == "__main__":
    main()

