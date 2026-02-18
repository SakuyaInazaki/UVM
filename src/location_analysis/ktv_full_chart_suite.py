#!/usr/bin/env python3
"""
Generate a full chart suite for KTV data analysis.

Outputs:
- 13 figures for spatial distribution, district patterns, Moran/LISA,
  sentiment, topic-sentiment, regression coefficients, heterogeneity.
- supporting tables and summary metrics.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_cache")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.spatial import cKDTree
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer

try:
    import jieba
except Exception:
    jieba = None


sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 130
plt.rcParams["savefig.dpi"] = 160
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.sans-serif"] = [
    "PingFang SC",
    "Heiti TC",
    "Arial Unicode MS",
    "Noto Sans CJK SC",
    "SimHei",
    "DejaVu Sans",
]


DEFAULT_SHOPS = "data/processed/dianping_ktv_shop_profile_beijing_20260218_enriched_offline_s0.csv"
DEFAULT_REVIEWS = "data/raw/dianping_ktv_reviews_beijing_recent100_20260213.csv"
DEFAULT_OUT_DIR = "data/processed/ktv_analysis_20260218"


CORE_DISTRICTS = {"东城区", "西城区", "朝阳区", "海淀区", "丰台区"}

POS_WORDS = ["好", "不错", "满意", "推荐", "干净", "舒服", "热情", "划算", "超值", "方便", "喜欢", "赞"]
NEG_WORDS = ["差", "一般", "脏", "吵", "贵", "失望", "不好", "糟糕", "慢", "坑", "不推荐", "态度差"]

STOPWORDS = {
    "我们", "你们", "他们", "然后", "而且", "这个", "那个", "还是", "就是", "真的", "非常", "比较", "感觉",
    "可以", "一个", "没有", "一下", "时候", "因为", "所以", "但是", "如果", "已经", "什么", "怎么", "还有",
    "这里", "那里", "不是", "不是很", "有点", "很多", "基本", "以及", "太", "很", "都", "也", "就", "又",
    "了", "的", "是", "在", "和", "与", "及", "啊", "呀", "吧",
}


@dataclass
class Paths:
    out_dir: Path
    fig_dir: Path
    table_dir: Path


def ensure_dirs(out_dir: str) -> Paths:
    out = Path(out_dir)
    figs = out / "figures"
    tables = out / "tables"
    figs.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    return Paths(out_dir=out, fig_dir=figs, table_dir=tables)


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def parse_package_count(packages: str, package_count: str) -> int:
    if isinstance(package_count, str) and package_count.strip():
        try:
            return int(float(package_count.strip()))
        except Exception:
            pass
    if not isinstance(packages, str) or not packages.strip():
        return 0
    try:
        arr = json.loads(packages)
        if isinstance(arr, list):
            return len(arr)
    except Exception:
        return 0
    return 0


def load_data(shops_path: str, reviews_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    shops = pd.read_csv(shops_path, encoding="utf-8-sig")
    reviews = pd.read_csv(reviews_path, encoding="utf-8-sig")

    for col in ["lng", "lat", "rating", "review_count", "avg_price"]:
        shops[col] = to_num(shops[col])

    shops["package_count_num"] = [
        parse_package_count(str(p), str(c))
        for p, c in zip(shops.get("packages", ""), shops.get("package_count", ""))
    ]

    reviews["score_avg_num"] = to_num(reviews["score_avg"])

    shop_review_rows = reviews.groupby("shop_id").size().rename("review_rows_from_reviews")
    shops = shops.merge(shop_review_rows, on="shop_id", how="left")
    shops["review_rows_from_reviews"] = shops["review_rows_from_reviews"].fillna(0).astype(int)

    # Keep spatially valid shops.
    shops = shops[
        shops["lng"].between(115.0, 118.5, inclusive="both")
        & shops["lat"].between(39.0, 41.5, inclusive="both")
    ].copy()

    # Fill review_count with observed review rows if missing.
    shops["review_count_filled"] = shops["review_count"].copy()
    m = shops["review_count_filled"].isna()
    shops.loc[m, "review_count_filled"] = shops.loc[m, "review_rows_from_reviews"]
    shops["review_count_filled"] = shops["review_count_filled"].fillna(0)

    return shops, reviews


def sentiment_label(score_avg: float, text: str) -> int:
    if not np.isnan(score_avg):
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


def build_sentiment(reviews: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    reviews = reviews.copy()
    reviews["sentiment"] = [
        sentiment_label(score, text)
        for score, text in zip(reviews["score_avg_num"].fillna(np.nan), reviews["content"])
    ]
    reviews["sentiment_label"] = reviews["sentiment"].map({-1: "Negative", 0: "Neutral", 1: "Positive"})

    by_shop = reviews.groupby("shop_id").agg(
        sentiment_mean=("sentiment", "mean"),
        pos_rate=("sentiment", lambda s: float((s == 1).mean())),
        neg_rate=("sentiment", lambda s: float((s == -1).mean())),
        sentiment_n=("sentiment", "size"),
    )
    by_shop = by_shop.reset_index()
    return reviews, by_shop


def save_fig(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight")
    plt.close()


def plot_spatial_scatter(shops: pd.DataFrame, out: Path) -> None:
    plt.figure(figsize=(10, 7))
    cvals = np.log1p(shops["review_count_filled"].values)
    plt.scatter(shops["lng"], shops["lat"], c=cvals, s=16, alpha=0.8, cmap="viridis")
    plt.colorbar(label="log(1+review_count)")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.title("KTV Point Distribution (Beijing)")
    save_fig(out / "01_spatial_scatter.png")


def plot_kde_heatmap(shops: pd.DataFrame, out: Path) -> None:
    plt.figure(figsize=(10, 7))
    sns.kdeplot(
        data=shops,
        x="lng",
        y="lat",
        fill=True,
        levels=14,
        thresh=0.03,
        cmap="YlOrRd",
        bw_adjust=0.8,
    )
    plt.scatter(shops["lng"], shops["lat"], s=8, alpha=0.25, color="black")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.title("KTV Kernel Density Heatmap")
    save_fig(out / "02_spatial_kde_heatmap.png")


def plot_district_charts(shops: pd.DataFrame, out: Path, tables: Path) -> None:
    district_counts = shops["district"].fillna("Unknown").value_counts().reset_index()
    district_counts.columns = ["district", "shop_count"]
    district_counts.to_csv(tables / "district_shop_count.csv", index=False, encoding="utf-8-sig")

    plt.figure(figsize=(12, 6))
    sns.barplot(data=district_counts, x="district", y="shop_count", color="#4C78A8")
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("District")
    plt.ylabel("Shop Count")
    plt.title("KTV Shop Count by District")
    save_fig(out / "03_district_shop_count_bar.png")

    rating_df = shops.dropna(subset=["rating"]).copy()
    top_districts = district_counts["district"].head(12).tolist()
    rating_df = rating_df[rating_df["district"].isin(top_districts)]
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=rating_df, x="district", y="rating", color="#72B7B2", showfliers=False)
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("District")
    plt.ylabel("Rating")
    plt.title("Rating Distribution by District")
    save_fig(out / "04_district_rating_box.png")

    rc_df = shops.copy()
    rc_df["log_reviews"] = np.log1p(rc_df["review_count_filled"])
    rc_df = rc_df[rc_df["district"].isin(top_districts)]
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=rc_df, x="district", y="log_reviews", color="#ECA15D", showfliers=False)
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("District")
    plt.ylabel("log(1+review_count)")
    plt.title("Review Count Distribution by District")
    save_fig(out / "05_district_reviewcount_box.png")


def standard_deviational_ellipse(shops: pd.DataFrame) -> Dict[str, float]:
    xy = shops[["lng", "lat"]].to_numpy()
    center = xy.mean(axis=0)
    cov = np.cov(xy.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    major_std = float(np.sqrt(eigvals[0]))
    minor_std = float(np.sqrt(eigvals[1]))
    angle = float(np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0])))
    return {
        "center_lng": float(center[0]),
        "center_lat": float(center[1]),
        "major_std": major_std,
        "minor_std": minor_std,
        "angle_deg": angle,
    }


def plot_std_ellipse(shops: pd.DataFrame, out: Path, tables: Path) -> None:
    stats = standard_deviational_ellipse(shops)
    center = np.array([stats["center_lng"], stats["center_lat"]])
    major = stats["major_std"]
    minor = stats["minor_std"]
    theta = np.radians(stats["angle_deg"])
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    t = np.linspace(0, 2 * np.pi, 300)
    ellipse = np.vstack([2.0 * major * np.cos(t), 2.0 * minor * np.sin(t)])
    ellipse_rot = (rot @ ellipse).T + center

    plt.figure(figsize=(10, 7))
    plt.scatter(shops["lng"], shops["lat"], s=10, alpha=0.45, color="#3E7CB1")
    plt.plot(ellipse_rot[:, 0], ellipse_rot[:, 1], color="#D62728", linewidth=2.0, label="2-SD Ellipse")
    plt.scatter([center[0]], [center[1]], color="black", s=36, label="Mean Center")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.title("Standard Deviational Ellipse")
    plt.legend()
    save_fig(out / "06_standard_deviational_ellipse.png")

    pd.DataFrame([stats]).to_csv(tables / "standard_deviational_ellipse_stats.csv", index=False, encoding="utf-8-sig")


def build_knn_weights(xy: np.ndarray, k: int = 8) -> np.ndarray:
    tree = cKDTree(xy)
    _, idx = tree.query(xy, k=k + 1)
    return idx[:, 1:]


def moran_global(z: np.ndarray, nbr_idx: np.ndarray) -> Tuple[float, np.ndarray]:
    n = len(z)
    k = nbr_idx.shape[1]
    lag = z[nbr_idx].mean(axis=1)
    s0 = float(n)  # row-standardized
    I = (n / s0) * float(np.sum(z * lag) / np.sum(z * z))
    return I, lag


def permutation_moran(z: np.ndarray, nbr_idx: np.ndarray, n_perm: int = 499, seed: int = 42) -> Tuple[float, float, np.ndarray]:
    rng = np.random.default_rng(seed)
    I_obs, _ = moran_global(z, nbr_idx)
    sims = np.zeros(n_perm, dtype=float)
    for i in range(n_perm):
        zp = rng.permutation(z)
        sims[i], _ = moran_global(zp, nbr_idx)
    p = (np.sum(np.abs(sims) >= abs(I_obs)) + 1.0) / (n_perm + 1.0)
    return I_obs, p, sims


def local_lisa(z: np.ndarray, nbr_idx: np.ndarray, n_perm: int = 199, seed: int = 123) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    lag = z[nbr_idx].mean(axis=1)
    local_i = z * lag
    n = len(z)
    sims = np.zeros((n, n_perm), dtype=float)
    for j in range(n_perm):
        zp = rng.permutation(z)
        lagp = zp[nbr_idx].mean(axis=1)
        sims[:, j] = zp * lagp
    pvals = (np.sum(np.abs(sims) >= np.abs(local_i[:, None]), axis=1) + 1.0) / (n_perm + 1.0)
    return local_i, pvals, lag


def plot_moran_lisa(shops: pd.DataFrame, out: Path, tables: Path) -> None:
    xy = shops[["lng", "lat"]].to_numpy()
    x = np.log1p(shops["review_count_filled"].to_numpy(dtype=float))
    z = x - x.mean()
    z = z / (z.std(ddof=0) + 1e-12)
    nbr_idx = build_knn_weights(xy, k=8)
    I, p, sims = permutation_moran(z, nbr_idx, n_perm=499, seed=2026)
    _, lag = moran_global(z, nbr_idx)

    # Moran scatter.
    plt.figure(figsize=(7.5, 7))
    plt.axhline(0, color="grey", linewidth=1)
    plt.axvline(0, color="grey", linewidth=1)
    plt.scatter(z, lag, s=12, alpha=0.5, color="#4C78A8")
    coef = np.polyfit(z, lag, 1)
    xx = np.linspace(z.min(), z.max(), 100)
    plt.plot(xx, coef[0] * xx + coef[1], color="#D62728", linewidth=2)
    plt.xlabel("Standardized log(1+review_count)")
    plt.ylabel("Spatial Lag")
    plt.title(f"Moran Scatter (I={I:.3f}, p={p:.3f})")
    save_fig(out / "07_moran_scatter.png")

    # LISA cluster map.
    local_i, pvals, lag_local = local_lisa(z, nbr_idx, n_perm=199, seed=2027)
    sig = pvals < 0.05
    quad = np.full(len(z), "NotSig", dtype=object)
    quad[(z > 0) & (lag_local > 0) & sig] = "HH"
    quad[(z < 0) & (lag_local < 0) & sig] = "LL"
    quad[(z > 0) & (lag_local < 0) & sig] = "HL"
    quad[(z < 0) & (lag_local > 0) & sig] = "LH"

    lisa_df = shops[["shop_id", "lng", "lat", "district"]].copy()
    lisa_df["local_i"] = local_i
    lisa_df["p_value"] = pvals
    lisa_df["cluster"] = quad
    lisa_df.to_csv(tables / "lisa_cluster_results.csv", index=False, encoding="utf-8-sig")

    palette = {"HH": "#D7191C", "LL": "#2C7BB6", "HL": "#FDAE61", "LH": "#ABD9E9", "NotSig": "#BDBDBD"}
    plt.figure(figsize=(10, 7))
    for c in ["NotSig", "HH", "LL", "HL", "LH"]:
        d = lisa_df[lisa_df["cluster"] == c]
        if d.empty:
            continue
        plt.scatter(d["lng"], d["lat"], s=14, alpha=0.8, color=palette[c], label=c)
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.title("LISA Cluster Map (review_count)")
    plt.legend(title="Cluster", ncol=3)
    save_fig(out / "08_lisa_cluster_map.png")

    # Save global Moran summary.
    pd.DataFrame(
        [{"moran_i": I, "p_value": p, "n_shops": len(shops), "k_neighbors": 8, "n_perm": 499}]
    ).to_csv(tables / "moran_global_summary.csv", index=False, encoding="utf-8-sig")


def plot_sentiment_distribution(reviews_sent: pd.DataFrame, out: Path, tables: Path) -> None:
    counts = reviews_sent["sentiment_label"].value_counts().reindex(["Positive", "Neutral", "Negative"]).fillna(0)
    sent_df = counts.reset_index()
    sent_df.columns = ["sentiment", "count"]
    sent_df["ratio"] = sent_df["count"] / sent_df["count"].sum()
    sent_df.to_csv(tables / "sentiment_distribution.csv", index=False, encoding="utf-8-sig")

    plt.figure(figsize=(7.5, 5.5))
    sns.barplot(
        data=sent_df,
        x="sentiment",
        y="count",
        hue="sentiment",
        palette=["#3BAA5C", "#9AA1A6", "#D84B3E"],
        dodge=False,
        legend=False,
    )
    plt.xlabel("Sentiment")
    plt.ylabel("Review Count")
    plt.title("Review Sentiment Distribution")
    save_fig(out / "09_sentiment_distribution.png")


def clean_text_for_lda(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_for_lda(text: str) -> str:
    t = clean_text_for_lda(text)
    if not t:
        return ""
    if jieba is None:
        chars = [c for c in t if "\u4e00" <= c <= "\u9fff"]
        grams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
        return " ".join(grams[:200])
    toks = []
    for w in jieba.lcut(t):
        w = w.strip()
        if len(w) < 2:
            continue
        if w in STOPWORDS:
            continue
        if w.isdigit():
            continue
        toks.append(w)
    return " ".join(toks[:200])


def build_lda_topic_sentiment_matrix(reviews_sent: pd.DataFrame, n_topics: int = 6, max_docs: int = 30000) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = reviews_sent[["content", "sentiment"]].copy()
    df["content"] = df["content"].fillna("").astype(str)
    df = df[df["content"].str.len() > 0]
    if len(df) > max_docs:
        df = df.sample(max_docs, random_state=2026)
    df["tokens"] = df["content"].map(tokenize_for_lda)
    df = df[df["tokens"].str.len() > 0].copy()
    if len(df) < max(200, n_topics * 10):
        empty = pd.DataFrame(
            [{"topic": "T1:insufficient_data", "mentions": 0, "positive_ratio": 0.0, "neutral_ratio": 0.0, "negative_ratio": 0.0, "mean_sentiment": 0.0}]
        )
        return empty, pd.DataFrame()

    vec = CountVectorizer(max_features=3000, min_df=20, max_df=0.90)
    X = vec.fit_transform(df["tokens"])
    if X.shape[0] < n_topics or X.shape[1] < n_topics:
        empty = pd.DataFrame(
            [{"topic": "T1:insufficient_vocab", "mentions": 0, "positive_ratio": 0.0, "neutral_ratio": 0.0, "negative_ratio": 0.0, "mean_sentiment": 0.0}]
        )
        return empty, pd.DataFrame()

    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=2026,
        learning_method="batch",
        max_iter=20,
    )
    doc_topic = lda.fit_transform(X)
    topic_id = doc_topic.argmax(axis=1)

    terms = np.array(vec.get_feature_names_out())
    topic_words_rows: List[Dict[str, str]] = []
    label_map: Dict[int, str] = {}
    for i, comp in enumerate(lda.components_):
        top_idx = np.argsort(comp)[-6:][::-1]
        words = terms[top_idx].tolist()
        label = f"T{i+1}:{'/'.join(words[:3])}"
        label_map[i] = label
        topic_words_rows.append({"topic_id": i, "topic": label, "top_words": " ".join(words)})

    df["topic_id"] = topic_id
    df["topic"] = df["topic_id"].map(label_map)

    agg = (
        df.groupby("topic")
        .agg(
            mentions=("sentiment", "size"),
            positive_ratio=("sentiment", lambda s: float((s == 1).mean())),
            neutral_ratio=("sentiment", lambda s: float((s == 0).mean())),
            negative_ratio=("sentiment", lambda s: float((s == -1).mean())),
            mean_sentiment=("sentiment", "mean"),
        )
        .reset_index()
        .sort_values("mentions", ascending=False)
    )

    topic_words = pd.DataFrame(topic_words_rows).sort_values("topic_id")
    return agg, topic_words


def plot_topic_sentiment_heatmap(reviews_sent: pd.DataFrame, out: Path, tables: Path) -> None:
    topic_df, topic_words = build_lda_topic_sentiment_matrix(reviews_sent, n_topics=6, max_docs=30000)
    topic_df.to_csv(tables / "topic_sentiment_matrix.csv", index=False, encoding="utf-8-sig")
    if not topic_words.empty:
        topic_words.to_csv(tables / "lda_topic_top_words.csv", index=False, encoding="utf-8-sig")

    heat = topic_df.set_index("topic")[["positive_ratio", "neutral_ratio", "negative_ratio"]]
    plt.figure(figsize=(9, 5.5))
    sns.heatmap(heat, annot=True, fmt=".2f", cmap="YlGnBu", cbar_kws={"label": "Ratio"})
    plt.title("LDA Topic-Sentiment Matrix")
    plt.xlabel("Sentiment Ratio")
    plt.ylabel("Topic")
    save_fig(out / "10_topic_sentiment_heatmap.png")


def ols_with_ci(X: np.ndarray, y: np.ndarray, col_names: List[str]) -> pd.DataFrame:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        y_hat = X @ beta
    resid = y - y_hat
    n, p = X.shape
    sigma2 = float((resid @ resid) / max(1, (n - p)))
    xtx_inv = np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(sigma2 * xtx_inv))
    out = pd.DataFrame({"term": col_names, "coef": beta, "se": se})
    out["ci_low"] = out["coef"] - 1.96 * out["se"]
    out["ci_high"] = out["coef"] + 1.96 * out["se"]
    return out


def plot_regression_forest(shops: pd.DataFrame, shop_sent: pd.DataFrame, out: Path, tables: Path) -> None:
    df = shops.merge(shop_sent, on="shop_id", how="left")
    df["core_dummy"] = df["district"].isin(CORE_DISTRICTS).astype(int)
    df["rating_f"] = df["rating"].fillna(df["rating"].median())
    df["avg_price_f"] = df["avg_price"].fillna(df["avg_price"].median())
    df["package_count_f"] = df["package_count_num"].fillna(0)
    df["pos_rate_f"] = df["pos_rate"].fillna(df["pos_rate"].mean())
    df["y"] = np.log1p(df["review_count_filled"].clip(lower=0))

    cols = ["Intercept", "rating_f", "avg_price_f", "package_count_f", "pos_rate_f", "core_dummy"]
    X = np.column_stack(
        [
            np.ones(len(df)),
            df["rating_f"].to_numpy(),
            df["avg_price_f"].to_numpy(),
            df["package_count_f"].to_numpy(),
            df["pos_rate_f"].to_numpy(),
            df["core_dummy"].to_numpy(),
        ]
    )
    y = df["y"].to_numpy()
    finite_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X = X[finite_mask]
    y = y[finite_mask]
    reg = ols_with_ci(X, y, cols)
    reg.to_csv(tables / "regression_coefficients.csv", index=False, encoding="utf-8-sig")

    vis = reg[reg["term"] != "Intercept"].copy()
    vis["term"] = vis["term"].map(
        {
            "rating_f": "Rating",
            "avg_price_f": "Avg Price",
            "package_count_f": "Package Count",
            "pos_rate_f": "Positive Sentiment Rate",
            "core_dummy": "Core District (1/0)",
        }
    )
    vis = vis.sort_values("coef")

    plt.figure(figsize=(8, 5.8))
    plt.hlines(y=vis["term"], xmin=vis["ci_low"], xmax=vis["ci_high"], color="#4C78A8", linewidth=2)
    plt.scatter(vis["coef"], vis["term"], color="#D62728", s=45)
    plt.axvline(0, color="grey", linestyle="--", linewidth=1)
    plt.xlabel("Coefficient (95% CI)")
    plt.ylabel("Feature")
    plt.title("OLS Coefficient Forest Plot\nDependent Var: log(1+review_count)")
    save_fig(out / "11_regression_coef_forest.png")


def plot_heterogeneity(shops: pd.DataFrame, shop_sent: pd.DataFrame, out: Path, tables: Path) -> None:
    df = shops.merge(shop_sent, on="shop_id", how="left")
    df["group"] = np.where(df["district"].isin(CORE_DISTRICTS), "Core", "Non-Core")
    df["log_reviews"] = np.log1p(df["review_count_filled"])

    summary = df.groupby("group").agg(
        shop_count=("shop_id", "size"),
        avg_rating=("rating", "mean"),
        avg_log_reviews=("log_reviews", "mean"),
        avg_pos_rate=("pos_rate", "mean"),
        avg_package_count=("package_count_num", "mean"),
    ).reset_index()
    summary.to_csv(tables / "heterogeneity_core_vs_noncore.csv", index=False, encoding="utf-8-sig")

    fig, axes = plt.subplots(2, 2, figsize=(10, 7.6))
    metrics = [
        ("avg_rating", "Average Rating"),
        ("avg_log_reviews", "Average log(1+review_count)"),
        ("avg_pos_rate", "Average Positive Sentiment Rate"),
        ("avg_package_count", "Average Package Count"),
    ]

    for ax, (col, title) in zip(axes.flatten(), metrics):
        sns.barplot(
            data=summary,
            x="group",
            y=col,
            hue="group",
            ax=ax,
            palette=["#4C78A8", "#F58518"],
            dodge=False,
            legend=False,
        )
        ax.set_title(title)
        ax.set_xlabel("")
        ax.set_ylabel("")

    plt.suptitle("Heterogeneity: Core vs Non-Core Districts", y=1.02)
    save_fig(out / "12_heterogeneity_core_noncore.png")


def plot_heterogeneity_rating_groups(shops: pd.DataFrame, shop_sent: pd.DataFrame, out: Path, tables: Path) -> None:
    df = shops.merge(shop_sent, on="shop_id", how="left")
    med_rating = float(df["rating"].dropna().median()) if df["rating"].notna().any() else 4.0
    df["rating_group"] = np.where(df["rating"].fillna(med_rating) >= med_rating, "HighRating", "LowRating")
    df["log_reviews"] = np.log1p(df["review_count_filled"])

    summary = df.groupby("rating_group").agg(
        shop_count=("shop_id", "size"),
        avg_rating=("rating", "mean"),
        avg_log_reviews=("log_reviews", "mean"),
        avg_pos_rate=("pos_rate", "mean"),
        avg_package_count=("package_count_num", "mean"),
    ).reset_index()
    summary.to_csv(tables / "heterogeneity_high_vs_low_rating.csv", index=False, encoding="utf-8-sig")

    fig, axes = plt.subplots(2, 2, figsize=(10, 7.6))
    metrics = [
        ("avg_rating", "Average Rating"),
        ("avg_log_reviews", "Average log(1+review_count)"),
        ("avg_pos_rate", "Average Positive Sentiment Rate"),
        ("avg_package_count", "Average Package Count"),
    ]
    for ax, (col, title) in zip(axes.flatten(), metrics):
        sns.barplot(
            data=summary,
            x="rating_group",
            y=col,
            hue="rating_group",
            ax=ax,
            palette=["#7A9E9F", "#EF8A62"],
            dodge=False,
            legend=False,
        )
        ax.set_title(title)
        ax.set_xlabel("")
        ax.set_ylabel("")

    plt.suptitle(f"Heterogeneity: High vs Low Rating (Median={med_rating:.2f})", y=1.02)
    save_fig(out / "13_heterogeneity_high_low_rating.png")


def write_run_summary(paths: Paths, shops: pd.DataFrame, reviews: pd.DataFrame) -> None:
    summary = {
        "n_shops_used": int(len(shops)),
        "n_reviews_used": int(len(reviews)),
        "output_figure_dir": str(paths.fig_dir),
        "output_table_dir": str(paths.table_dir),
    }
    with open(paths.out_dir / "run_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate full KTV analysis chart suite.")
    parser.add_argument("--shops", default=DEFAULT_SHOPS)
    parser.add_argument("--reviews", default=DEFAULT_REVIEWS)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    paths = ensure_dirs(args.out_dir)
    shops, reviews = load_data(args.shops, args.reviews)
    reviews_sent, shop_sent = build_sentiment(reviews)

    plot_spatial_scatter(shops, paths.fig_dir)
    plot_kde_heatmap(shops, paths.fig_dir)
    plot_district_charts(shops, paths.fig_dir, paths.table_dir)
    plot_std_ellipse(shops, paths.fig_dir, paths.table_dir)
    plot_moran_lisa(shops, paths.fig_dir, paths.table_dir)
    plot_sentiment_distribution(reviews_sent, paths.fig_dir, paths.table_dir)
    plot_topic_sentiment_heatmap(reviews_sent, paths.fig_dir, paths.table_dir)
    plot_regression_forest(shops, shop_sent, paths.fig_dir, paths.table_dir)
    plot_heterogeneity(shops, shop_sent, paths.fig_dir, paths.table_dir)
    plot_heterogeneity_rating_groups(shops, shop_sent, paths.fig_dir, paths.table_dir)
    write_run_summary(paths, shops, reviews)

    print(f"done figures={paths.fig_dir}")
    print(f"done tables={paths.table_dir}")


if __name__ == "__main__":
    main()
