"""
股票動能分析系統 v2
新增功能：搜尋紀錄、自選清單、一鍵掃描、價格警示
"""

import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from supabase import create_client

# ─────────────────────────────────────────────
#  Supabase 連線
# ─────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

db = get_supabase()

# ─────────────────────────────────────────────
#  頁面設定
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="股票動能分析系統",
    page_icon="📡",
    layout="wide",
)

st.title("📡 股票動能分析系統")
st.caption("支援台股（如 2330）與美股（如 NVDA）｜指標：Force Index EMA、ATR 停損、部位控管")

# ─────────────────────────────────────────────
#  側邊欄
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 參數設定")

    capital = st.number_input(
        "總本金（元）",
        min_value=100_000, max_value=100_000_000,
        value=1_000_000, step=100_000, format="%d",
    )
    risk_pct = st.slider("單筆最大虧損（佔本金 %）", 0.5, 5.0, 2.0, 0.5) / 100
    atr_mult = st.slider("ATR 停損倍數", 1.0, 4.0, 2.5, 0.5)
    fi_period = st.selectbox("Force Index EMA 週期", [2, 13, 26], index=1)
    atr_period = st.selectbox("ATR 週期", [7, 14, 21], index=1)
    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y"}
    data_period = period_map[st.selectbox("K線資料範圍", list(period_map.keys()), index=2)]
    lot_size = st.radio("每張股數", [1000, 1], index=0, help="台股選 1000；美股選 1")

    st.divider()
    st.subheader("⭐ 自選清單")
    try:
        watchlist_rows = db.table("watchlist").select("*").order("added_at", desc=True).execute().data
    except:
        watchlist_rows = []

    if watchlist_rows:
        for row in watchlist_rows:
            col_w, col_del = st.columns([3, 1])
            col_w.write(f"`{row['symbol']}` {row['name']}")
            if col_del.button("✕", key=f"del_{row['id']}"):
                db.table("watchlist").delete().eq("id", row["id"]).execute()
                st.rerun()
    else:
        st.caption("尚無自選股")

    st.divider()
    st.subheader("🕘 搜尋紀錄")
    try:
        history_rows = db.table("search_history").select("*").order("searched_at", desc=True).limit(10).execute().data
    except:
        history_rows = []

    if history_rows:
        for row in history_rows:
            st.caption(f"`{row['symbol']}` {row['name']}")
    else:
        st.caption("尚無搜尋紀錄")


# ─────────────────────────────────────────────
#  工具函式
# ─────────────────────────────────────────────

def parse_symbol(raw: str) -> tuple[str, str]:
    raw = raw.strip().upper()
    if raw.isdigit():
        return f"{raw}.TW", "台股"
    return raw, "美股"


@st.cache_data(ttl=300)
def fetch_data(symbol: str, period: str):
    try:
        df = yf.download(symbol, period=period, auto_adjust=True, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.index = pd.to_datetime(df.index.date)
        return df
    except Exception:
        return None


def get_company_name(symbol: str) -> str:
    try:
        return yf.Ticker(symbol).info.get("shortName", symbol)
    except:
        return symbol


def calc_fi_ema(df, period):
    return (df["Volume"] * df["Close"].diff()).ewm(span=period, adjust=False).mean()


def calc_atr(df, period):
    prev_c = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_c).abs(),
        (df["Low"] - prev_c).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def detect_divergence(close, fi_ema, lookback=10):
    if len(close) < lookback:
        return "資料不足"
    c, f = close.iloc[-lookback:], fi_ema.iloc[-lookback:]
    if (c.iloc[-1] > c.iloc[:-1].max()) and (f.iloc[-1] < f.iloc[:-1].max()):
        return "⚠️ 頂背離（邊拉邊出）"
    if (c.iloc[-1] < c.iloc[:-1].min()) and (f.iloc[-1] > f.iloc[:-1].min()):
        return "👀 底背離（邊跌邊買）"
    return "✅ 無明顯背離"


def calc_position(last_close, atr):
    stop_dist = atr * atr_mult
    stop_loss = last_close - stop_dist
    shares = (capital * risk_pct) / stop_dist if stop_dist > 0 else 0
    lots = max(1, int(shares // lot_size))
    return stop_loss, lots * lot_size * stop_dist, lots


def render_analysis(symbol: str, market: str, df, company_name: str):
    fi_ema = calc_fi_ema(df, fi_period)
    atr_series = calc_atr(df, atr_period)
    divergence = detect_divergence(df["Close"], fi_ema)

    last_close = float(df["Close"].iloc[-1])
    last_fi = float(fi_ema.iloc[-1])
    last_atr = float(atr_series.iloc[-1])
    fi_slope = float(fi_ema.iloc[-1] - fi_ema.iloc[-3])
    stop_loss, actual_risk, lots = calc_position(last_close, last_atr)

    momentum = ("🟢 多頭動能" if last_fi > 0 and fi_slope > 0
                else "🔴 空頭動能" if last_fi < 0 and fi_slope < 0
                else "🟡 中性觀望")

    st.divider()
    col_title, col_add = st.columns([4, 1])
    col_title.subheader(f"{company_name}（{symbol}）｜{market}")

    already_in = any(r["symbol"] == symbol for r in watchlist_rows)
    if not already_in:
        if col_add.button("⭐ 加入自選", key=f"add_{symbol}"):
            db.table("watchlist").insert({"symbol": symbol, "name": company_name}).execute()
            st.toast(f"{symbol} 已加入自選清單")
            st.rerun()
    else:
        col_add.success("已在自選")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("收盤價", f"{last_close:.2f}")
    c2.metric("ATR（波動度）", f"{last_atr:.2f}")
    c3.metric("建議停損", f"{stop_loss:.2f}", delta=f"-{last_atr*atr_mult:.2f}", delta_color="inverse")
    c4.metric(f"建議部位（{'張' if lot_size==1000 else '股'}）", f"{lots}")

    col_m, col_d, col_r = st.columns(3)
    col_m.info(f"**動能狀態**：{momentum}")
    if "背離" in divergence and "無" not in divergence:
        col_d.warning(f"**背離訊號**：{divergence}")
    else:
        col_d.success(f"**背離訊號**：{divergence}")
    col_r.info(f"**最大風險**：{actual_risk:,.0f} 元（本金 {risk_pct*100:.0f}%）")

    with st.expander("🔔 設定價格警示"):
        col_p, col_dir, col_btn = st.columns([2, 2, 1])
        target_price = col_p.number_input("目標價", value=float(round(last_close*0.95, 1)), key=f"tp_{symbol}")
        direction = col_dir.selectbox("條件", ["跌破此價格", "突破此價格"], key=f"dir_{symbol}")
        if col_btn.button("設定", key=f"alert_{symbol}"):
            db.table("alerts").insert({
                "symbol": symbol, "name": company_name,
                "target_price": target_price, "direction": direction,
            }).execute()
            st.toast(f"警示已設定：{symbol} {direction} {target_price}")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.55, 0.25, 0.20], vertical_spacing=0.03,
                        subplot_titles=("K線 + 停損線", f"Force Index EMA（{fi_period}）", "成交量"))

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="K線", increasing_line_color="#ef5350", decreasing_line_color="#26a69a",
    ), row=1, col=1)
    fig.add_hline(y=stop_loss, line_dash="dash", line_color="orange", line_width=1.5,
                  annotation_text=f"停損 {stop_loss:.2f}", annotation_position="right", row=1, col=1)

    fi_colors = ["#ef5350" if v >= 0 else "#26a69a" for v in fi_ema]
    fig.add_trace(go.Bar(x=fi_ema.index, y=fi_ema.values, marker_color=fi_colors, name="FI EMA"), row=2, col=1)
    fig.add_hline(y=0, line_color="gray", line_width=0.8, row=2, col=1)

    vol_colors = ["#ef5350" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#26a69a" for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=vol_colors, name="成交量"), row=3, col=1)

    fig.update_layout(height=700, showlegend=False, xaxis_rangeslider_visible=False,
                      plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#fafafa")
    fig.update_xaxes(gridcolor="#2a2a2a")
    fig.update_yaxes(gridcolor="#2a2a2a")
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
#  主畫面 Tab
# ─────────────────────────────────────────────

tab_search, tab_watchlist, tab_alerts = st.tabs(["🔍 查詢股票", "⭐ 自選清單掃描", "🔔 價格警示"])

with tab_search:
    col_input, col_btn = st.columns([3, 1])
    raw_input = col_input.text_input("代號", placeholder="台股輸入數字（如 2330），美股輸入英文（如 NVDA）", label_visibility="collapsed")
    run = col_btn.button("開始分析", use_container_width=True, type="primary")

    if run and raw_input:
        symbol, market = parse_symbol(raw_input)
        with st.spinner(f"正在抓取 {symbol} 資料..."):
            df = fetch_data(symbol, data_period)
        if df is None or len(df) < 30:
            st.error(f"❌ 找不到 **{symbol}** 的資料，請確認代號是否正確。")
        else:
            company_name = get_company_name(symbol)
            try:
                db.table("search_history").insert({"symbol": symbol, "name": company_name}).execute()
                all_rows = db.table("search_history").select("id").order("searched_at", desc=False).execute().data
                if len(all_rows) > 20:
                    for old in all_rows[:len(all_rows)-20]:
                        db.table("search_history").delete().eq("id", old["id"]).execute()
            except:
                pass
            render_analysis(symbol, market, df, company_name)
    elif run:
        st.warning("請輸入股票代號")

with tab_watchlist:
    if not watchlist_rows:
        st.info("自選清單是空的，先查詢股票後點「⭐ 加入自選」。")
    else:
        if st.button("🔄 一鍵掃描所有自選股", type="primary"):
            for row in watchlist_rows:
                sym = row["symbol"]
                market = "台股" if sym.endswith(".TW") else "美股"
                with st.spinner(f"分析 {sym}..."):
                    df = fetch_data(sym, data_period)
                if df is not None and len(df) >= 30:
                    render_analysis(sym, market, df, row["name"])
                else:
                    st.warning(f"{sym} 資料抓取失敗，跳過")

with tab_alerts:
    try:
        alert_rows = db.table("alerts").select("*").order("created_at", desc=True).execute().data
    except:
        alert_rows = []

    if not alert_rows:
        st.info("尚無警示，可在查詢結果頁面展開「設定價格警示」新增。")
    else:
        st.write(f"共 {len(alert_rows)} 個警示：")
        for row in alert_rows:
            df_check = fetch_data(row["symbol"], "5d")
            current_price = float(df_check["Close"].iloc[-1]) if df_check is not None else None
            col_s, col_t, col_c, col_status, col_del = st.columns([1.5, 1.5, 1.5, 2, 1])
            col_s.write(f"**{row['symbol']}**")
            col_t.write(f"目標：{row['target_price']}")
            col_c.write(f"現價：{current_price:.2f}" if current_price else "無法取得")
            if current_price:
                triggered = (
                    (row["direction"] == "跌破此價格" and current_price < row["target_price"]) or
                    (row["direction"] == "突破此價格" and current_price > row["target_price"])
                )
                col_status.error(f"🚨 已{row['direction']}！") if triggered else col_status.success("監控中")
            if col_del.button("刪除", key=f"del_alert_{row['id']}"):
                db.table("alerts").delete().eq("id", row["id"]).execute()
                st.rerun()
