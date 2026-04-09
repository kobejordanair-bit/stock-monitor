"""
股票動能分析系統
支援台股（輸入四碼，如 2330）與美股（輸入代號，如 NVDA）
指標：Force Index EMA、ATR 動態停損、科學部位控管
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
#  側邊欄：參數設定
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 參數設定")

    capital = st.number_input(
        "總本金（元）",
        min_value=100_000,
        max_value=100_000_000,
        value=1_000_000,
        step=100_000,
        format="%d",
    )

    risk_pct = st.slider(
        "單筆最大虧損（佔本金 %）",
        min_value=0.5,
        max_value=5.0,
        value=2.0,
        step=0.5,
    ) / 100

    atr_mult = st.slider(
        "ATR 停損倍數",
        min_value=1.0,
        max_value=4.0,
        value=2.5,
        step=0.5,
    )

    fi_period = st.selectbox(
        "Force Index EMA 週期",
        options=[2, 13, 26],
        index=1,
    )

    atr_period = st.selectbox(
        "ATR 週期",
        options=[7, 14, 21],
        index=1,
    )

    period_map = {
        "1 個月": "1mo",
        "3 個月": "3mo",
        "6 個月": "6mo",
        "1 年": "1y",
    }
    data_period_label = st.selectbox("K線資料範圍", list(period_map.keys()), index=2)
    data_period = period_map[data_period_label]

    lot_size = st.radio("每張股數", [1000, 1], index=0, help="台股選 1000；美股選 1")

# ─────────────────────────────────────────────
#  主畫面：輸入區
# ─────────────────────────────────────────────

col_input, col_btn = st.columns([3, 1])

with col_input:
    raw_input = st.text_input(
        "輸入股票代號",
        placeholder="台股輸入四碼（如 2330），美股輸入英文代號（如 NVDA）",
        label_visibility="collapsed",
    )

with col_btn:
    run = st.button("🔍 開始分析", use_container_width=True, type="primary")

# ─────────────────────────────────────────────
#  工具函式
# ─────────────────────────────────────────────

def parse_symbol(raw: str) -> tuple[str, str]:
    """
    判斷台股或美股，回傳 (yfinance_symbol, 市場名稱)
    台股：純數字四碼 → 加 .TW
    美股：英文字母 → 直接用
    """
    raw = raw.strip().upper()
    if raw.isdigit():
        return f"{raw}.TW", "台股"
    return raw, "美股"


@st.cache_data(ttl=300)
def fetch_data(symbol: str, period: str) -> pd.DataFrame | None:
    try:
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ticker = yf.Ticker(symbol, session=session)
        df = ticker.history(period=period)
        if df.empty:
            # 重試一次，有時候第一次會失敗
            import time
            time.sleep(2)
            df = ticker.history(period=period)
        if df.empty:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.index = pd.to_datetime(df.index.date)
        return df
    except Exception:
        return None


def calc_fi_ema(df: pd.DataFrame, period: int) -> pd.Series:
    fi_raw = df["Volume"] * df["Close"].diff()
    return fi_raw.ewm(span=period, adjust=False).mean()


def calc_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_c = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_c).abs(),
        (df["Low"] - prev_c).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def detect_divergence(close: pd.Series, fi_ema: pd.Series, lookback: int = 10) -> str:
    if len(close) < lookback:
        return "資料不足"
    c = close.iloc[-lookback:]
    f = fi_ema.iloc[-lookback:]
    bearish = (c.iloc[-1] > c.iloc[:-1].max()) and (f.iloc[-1] < f.iloc[:-1].max())
    bullish = (c.iloc[-1] < c.iloc[:-1].min()) and (f.iloc[-1] > f.iloc[:-1].min())
    if bearish:
        return "⚠️ 頂背離（邊拉邊出）"
    if bullish:
        return "👀 底背離（邊跌邊買）"
    return "✅ 無明顯背離"


def calc_position(last_close, atr, capital, risk_pct, atr_mult, lot_size):
    stop_dist = atr * atr_mult
    stop_loss = last_close - stop_dist
    max_risk = capital * risk_pct
    shares = max_risk / stop_dist if stop_dist > 0 else 0
    lots = max(1, int(shares // lot_size))
    actual_risk = lots * lot_size * stop_dist
    return stop_loss, actual_risk, lots


# ─────────────────────────────────────────────
#  主分析流程
# ─────────────────────────────────────────────

if run and raw_input:
    symbol, market = parse_symbol(raw_input)

    with st.spinner(f"正在抓取 {symbol} 資料..."):
        df = fetch_data(symbol, data_period)

    if df is None or len(df) < 30:
        st.error(f"❌ 找不到 **{symbol}** 的資料，請確認代號是否正確。")
        st.stop()

    # 計算指標
    fi_ema = calc_fi_ema(df, fi_period)
    atr_series = calc_atr(df, atr_period)
    divergence = detect_divergence(df["Close"], fi_ema)

    last_close = df["Close"].iloc[-1]
    last_fi = fi_ema.iloc[-1]
    last_atr = atr_series.iloc[-1]
    fi_slope = fi_ema.iloc[-1] - fi_ema.iloc[-3]

    stop_loss, actual_risk, lots = calc_position(
        last_close, last_atr, capital, risk_pct, atr_mult, lot_size
    )

    # 動能判斷
    if last_fi > 0 and fi_slope > 0:
        momentum = "🟢 多頭動能"
        momentum_color = "green"
    elif last_fi < 0 and fi_slope < 0:
        momentum = "🔴 空頭動能"
        momentum_color = "red"
    else:
        momentum = "🟡 中性觀望"
        momentum_color = "orange"

    # ── 標題列 ──
    st.divider()
    ticker_info = yf.Ticker(symbol).info
    company_name = ticker_info.get("shortName", symbol)
    st.subheader(f"{company_name}（{symbol}）｜{market}")

    # ── 四格指標卡 ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("收盤價", f"{last_close:.2f}")
    c2.metric("ATR（波動度）", f"{last_atr:.2f}")
    c3.metric("建議停損", f"{stop_loss:.2f}", delta=f"-{last_atr * atr_mult:.2f}", delta_color="inverse")
    c4.metric(f"建議部位（{'張' if lot_size == 1000 else '股'}）", f"{lots}")

    # ── 訊號列 ──
    col_m, col_d, col_r = st.columns(3)
    col_m.info(f"**動能狀態**：{momentum}")
    if "背離" in divergence and "無" not in divergence:
        col_d.warning(f"**背離訊號**：{divergence}")
    else:
        col_d.success(f"**背離訊號**：{divergence}")
    col_r.info(f"**最大風險**：{actual_risk:,.0f} 元（本金 {risk_pct*100:.0f}%）")

    # ── 圖表 ──
    st.divider()
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.25, 0.20],
        vertical_spacing=0.03,
        subplot_titles=("K線 + 停損線", f"Force Index EMA（{fi_period}）", "成交量"),
    )

    # K線
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="K線", increasing_line_color="#ef5350", decreasing_line_color="#26a69a",
    ), row=1, col=1)

    # 停損線
    fig.add_hline(
        y=stop_loss, line_dash="dash", line_color="orange", line_width=1.5,
        annotation_text=f"停損 {stop_loss:.2f}", annotation_position="right",
        row=1, col=1,
    )

    # Force Index EMA
    fi_colors = ["#ef5350" if v >= 0 else "#26a69a" for v in fi_ema]
    fig.add_trace(go.Bar(
        x=fi_ema.index, y=fi_ema.values,
        marker_color=fi_colors, name="FI EMA",
    ), row=2, col=1)
    fig.add_hline(y=0, line_color="gray", line_width=0.8, row=2, col=1)

    # 成交量
    vol_colors = ["#ef5350" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#26a69a"
                  for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors, name="成交量",
    ), row=3, col=1)

    fig.update_layout(
        height=700,
        showlegend=False,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#fafafa",
    )
    fig.update_xaxes(gridcolor="#2a2a2a")
    fig.update_yaxes(gridcolor="#2a2a2a")

    st.plotly_chart(fig, use_container_width=True)

    # ── 說明 ──
    with st.expander("📖 指標說明"):
        st.markdown("""
**Force Index EMA（力道指數）**
> 計算公式：`成交量 × (今收 - 昨收)`，再取 EMA。正值代表買方主導，負值代表賣方主導。
> 「頂背離」= 股價創新高但 FI EMA 未跟上，代表大戶動能衰竭，是最常見的出貨訊號。

**ATR 動態停損**
> ATR 衡量股票真實波動幅度。停損 = 收盤價 - ATR × 倍數。波動大時停損自動拉遠，避免被雜訊洗掉。

**科學部位控管**
> 單筆最大虧損 = 本金 × 風險比例。根據停損距離反推最大持有股數，確保判斷錯誤時損失可控。
        """)

elif run and not raw_input:
    st.warning("請輸入股票代號")
