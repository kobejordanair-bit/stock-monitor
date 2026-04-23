"""
股票動能分析系統 v2
Supabase 改用 REST API，不需要 supabase 套件
"""

import os
import requests as req
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────
#  Supabase REST API（不需要 supabase 套件）
# ─────────────────────────────────────────────

def _get_secret(key: str) -> str:
    try:
        return st.secrets[key].strip()
    except Exception:
        return os.environ.get(key, "").strip()

SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

def db_select(table: str, order_col: str = None, desc: bool = True, limit: int = 100) -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        params = {"select": "*", "limit": limit}
        if order_col:
            params["order"] = f"{order_col}.{'desc' if desc else 'asc'}"
        r = req.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params, timeout=5)
        return r.json() if r.ok else []
    except Exception:
        return []

def db_insert(table: str, data: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        r = req.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), json=data, timeout=5)
        if not r.ok:
            st.error(f"DB錯誤：{r.status_code} {r.text}")
        return r.ok
    except Exception:
        return False

def db_delete(table: str, row_id: int) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        r = req.delete(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params={"id": f"eq.{row_id}"}, timeout=5)
        return r.ok
    except Exception:
        return False

# ─────────────────────────────────────────────
#  頁面設定
# ─────────────────────────────────────────────

st.set_page_config(page_title="股票動能分析系統", page_icon="📡", layout="wide")
# session_state 初始化
if "symbol" not in st.session_state:
    st.session_state.symbol = None
    st.session_state.market = None
    st.session_state.company = None


# 手機版 CSS 優化
st.markdown("""
<style>
/* 手機版字體放大 */
@media (max-width: 768px) {
    .stMetric { padding: 8px 4px !important; }
    .stMetric label { font-size: 12px !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 20px !important; }
    .stButton button { font-size: 16px !important; padding: 10px !important; }
    .stTextInput input { font-size: 16px !important; }
    h1 { font-size: 24px !important; }
    h2 { font-size: 18px !important; }
    h3 { font-size: 16px !important; }
    /* 側邊欄在手機預設收起 */
    [data-testid="stSidebar"] { min-width: 0 !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("📡 股票動能分析系統")
st.caption("支援台股（如 2330）與美股（如 NVDA）｜指標：Force Index EMA、ATR 停損、部位控管")
with st.expander("📖 使用說明與功能介紹"):
    st.markdown("""
### 🔍 查詢股票
輸入股票代號後點「開始分析」，台股輸入數字（如 `2330`），美股輸入英文（如 `NVDA`）。

### ⭐ 自選清單
分析完後點右上角「加入自選」可儲存股票。左側欄直接點股票名稱即可快速查詢，點 ✕ 刪除。

### 🔄 自選清單掃描
切換到「自選清單掃描」Tab，一鍵掃描所有自選股，不用一支一支查。

### 🔔 價格警示
分析結果頁面展開「設定價格警示」，設定目標價與條件（突破或跌破）。切換到「價格警示」Tab 可查看所有警示的即時狀態。

---

### 📊 指標詳細說明

**🟢 綜合訊號（最重要）**
三個指標同時看多 → 「強力買進訊號」；同時看空 → 「強力賣出訊號」。
只有一兩個指標同向則顯示「謹慎偏多/空」。**建議只在三指標同向時才行動，單一指標說買不算數。**

---

**Force Index EMA（力道指數）**
計算公式：`成交量 × (今收 - 昨收)`，再取 EMA 平滑。
- 正值：買方主導，資金在推動股價上漲
- 負值：賣方主導，資金在壓低股價
- **頂背離**：股價創新高，但 FI EMA 沒有跟上 → 代表大戶在出貨，是最常見的假突破警訊
- **底背離**：股價創新低，但 FI EMA 沒有跟著創低 → 代表低檔有買盤悄悄進場

---

**RSI（相對強弱指數，14日）**
衡量近期漲幅相對於跌幅的比例，數值在 0～100 之間。
- **高於 70**：超買區，股價漲太快，短期可能回調，不適合追高
- **低於 30**：超賣區，股價跌太深，短期可能反彈，可以留意買點
- **30～70**：正常區間，搭配其他指標判斷
- 重點：RSI 超買不代表一定會跌，超賣不代表一定會漲，要搭配 FI 和 MACD 確認

---

**MACD（指數平滑異同移動平均線，12/26/9）**
用快線（12日EMA）減慢線（26日EMA）得到 MACD 線，再對 MACD 線取 9 日 EMA 得到訊號線。
- **金叉**：MACD 線從下往上穿越訊號線 → 短期動能轉強，看多訊號
- **死叉**：MACD 線從上往下穿越訊號線 → 短期動能轉弱，看空訊號
- **柱狀圖（Histogram）**：MACD 線與訊號線的差距，紅色擴大代表多頭加速，縮小代表動能衰竭

---

**ATR 動態停損**
ATR 衡量股票真實波動幅度。停損 = 收盤價 - ATR × 倍數。
波動大時停損自動拉遠，避免被雜訊洗掉；波動小時停損拉近，保護獲利。
建議倍數 2.5，如果個股波動特別大可調到 3。

---

**科學部位控管**
單筆最大虧損 = 本金 × 風險比例，根據停損距離反推最大持有股數。
建議每筆風險不超過本金 2%，這樣即使連續錯 10 次，本金只損失約 20%，不會一次賠光。

---

### ⚙️ 左側參數設定
- **總本金**：你的實際投入資金
- **單筆最大虧損**：建議設 2%，即每筆交易最多虧本金的 2%
- **ATR 停損倍數**：建議 2.5，波動劇烈時可調高到 3
- **每張股數**：台股選 1000，美股選 1
    """)
# ─────────────────────────────────────────────
#  側邊欄
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 參數設定")
    capital = st.number_input("總本金（元）", min_value=100_000, max_value=100_000_000, value=1_000_000, step=100_000, format="%d")
    risk_pct = st.slider("單筆最大虧損（佔本金 %）", 0.5, 5.0, 2.0, 0.5) / 100
    atr_mult = st.slider("ATR 停損倍數", 1.0, 4.0, 2.5, 0.5)
    fi_period = st.selectbox("Force Index EMA 週期", [2, 13, 26], index=1)
    atr_period = st.selectbox("ATR 週期", [7, 14, 21], index=1)
    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y"}
    data_period = period_map[st.selectbox("K線資料範圍", list(period_map.keys()), index=2)]
    lot_size = st.radio("每張股數", [1000, 1], index=0, help="台股選 1000；美股選 1")

    st.divider()
    st.subheader("📊 圖表指標")
    timeframe = st.radio("K線週期", ["日線", "週線", "月線"], index=0, horizontal=True)
    show_ma = st.multiselect("均線", [5, 20, 60], default=[5, 20, 60])
    show_bb = st.checkbox("布林通道（20,2）", value=True)

    st.divider()
    st.subheader("⭐ 自選清單")
    watchlist_rows = db_select("watchlist", order_col="added_at", desc=True)
    if not SUPABASE_KEY:
        st.caption("⚠️ 資料庫未設定")
    if watchlist_rows:
        for row in watchlist_rows:
            col_w, col_del = st.columns([3, 1])
            if col_w.button(f"`{row['symbol']}` {row['name']}", key=f"watch_{row['id']}"):
                st.session_state.symbol = row["symbol"]
                st.session_state.market = "台股" if row["symbol"].endswith(".TW") else "美股"
                st.session_state.company = row["name"]
                st.rerun()
            if col_del.button("✕", key=f"del_{row['id']}"):
                db_delete("watchlist", row["id"])
                st.rerun()
    else:
        st.caption("尚無自選股")

    st.divider()
    st.subheader("🕘 搜尋紀錄")
    history_rows = db_select("search_history", order_col="searched_at", desc=True, limit=10)
    if history_rows:
        for row in history_rows:
            st.caption(f"`{row['symbol']}` {row['name']}")
    else:
        st.caption("尚無搜尋紀錄" if SUPABASE_KEY else "⚠️ 資料庫未設定")

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
        # 台股用 twstock
        if symbol.endswith(".TW"):
            import twstock
            code = symbol.replace(".TW", "")
            stock = twstock.Stock(code)
            # 依 period 決定抓幾個月
            months = {"1mo": 1, "3mo": 3, "6mo": 6, "1y": 12}.get(period, 6)
            from datetime import date
            today = date.today()
            year = today.year
            month = today.month - months
            if month <= 0:
                year -= 1
                month += 12
            stock.fetch_from(year, month)
            if not stock.date:
                return None
            df = pd.DataFrame({
                "Open": stock.open,
                "High": stock.high,
                "Low": stock.low,
                "Close": stock.price,
                "Volume": stock.capacity,
            }, index=pd.to_datetime(stock.date))
            df.index = pd.to_datetime(df.index.date)
            return df.dropna()
        # 美股用 yfinance
        else:
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
@st.cache_data(ttl=86400)
def get_company_name(symbol: str) -> str:
    try:
        if symbol.endswith(".TW"):
            import twstock
            code = symbol.replace(".TW", "")
            return twstock.codes[code].name if code in twstock.codes else symbol
        return yf.Ticker(symbol).info.get("shortName", symbol)
    except:
        return symbol

def calc_fi_ema(df, period):
    return (df["Volume"] * df["Close"].diff()).ewm(span=period, adjust=False).mean()

def calc_atr(df, period):
    prev_c = df["Close"].shift(1)
    tr = pd.concat([df["High"]-df["Low"], (df["High"]-prev_c).abs(), (df["Low"]-prev_c).abs()], axis=1).max(axis=1)
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


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period-1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period-1, adjust=False).mean()
    rs = gain / loss.where(loss != 0, other=np.nan)
    return rs.apply(lambda x: 100 if np.isnan(x) else 100 - 100 / (1 + x))

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def get_composite_signal(fi_momentum: str, rsi: float, macd_line: float, signal_line: float) -> tuple[str, str]:
    """
    三指標交叉驗證，回傳 (訊號, 說明)
    買進條件：FI 多頭 + RSI 未超買（<70）+ MACD 金叉或正值
    賣出條件：FI 空頭 + RSI 未超賣（>30）+ MACD 死叉或負值
    """
    fi_bull = "多頭" in fi_momentum
    fi_bear = "空頭" in fi_momentum
    rsi_ok_buy = rsi < 70
    rsi_ok_sell = rsi > 30
    macd_bull = macd_line > signal_line
    macd_bear = macd_line < signal_line

    if fi_bull and rsi_ok_buy and macd_bull:
        return "🟢 強力買進訊號", f"三指標同向看多｜RSI {rsi:.1f}（未超買）"
    elif fi_bear and rsi_ok_sell and macd_bear:
        return "🔴 強力賣出訊號", f"三指標同向看空｜RSI {rsi:.1f}（未超賣）"
    elif fi_bull and (not macd_bull or not rsi_ok_buy):
        return "🟡 謹慎偏多", f"FI 看多但 RSI {rsi:.1f} 或 MACD 未確認"
    elif fi_bear and (not macd_bear or not rsi_ok_sell):
        return "🟡 謹慎偏空", f"FI 看空但 RSI {rsi:.1f} 或 MACD 未確認"
    else:
        return "⚪ 訊號不明", f"指標分歧，建議觀望｜RSI {rsi:.1f}"

def calc_ma(close, periods):
    return {p: close.rolling(p).mean() for p in periods}

def calc_bollinger(close, period=20, std=2):
    ma = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    return ma + std * sigma, ma, ma - std * sigma

def resample_ohlcv(df, timeframe: str):
    if timeframe == "日線":
        return df
    freq = "W-FRI" if timeframe == "週線" else "ME"
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    try:
        return df.resample(freq).agg(agg).dropna()
    except ValueError:
        return df.resample("M").agg(agg).dropna()

def calc_position(last_close, atr):
    stop_dist = atr * atr_mult
    stop_loss = last_close - stop_dist
    shares = (capital * risk_pct) / stop_dist if stop_dist > 0 else 0
    lots = max(1, int(shares // lot_size))
    return stop_loss, lots * lot_size * stop_dist, lots

def render_analysis(symbol: str, market: str, df, company_name: str):
    df = resample_ohlcv(df, timeframe)
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

    # RSI + MACD
    rsi_series = calc_rsi(df["Close"])
    macd_line, signal_line, macd_hist = calc_macd(df["Close"])
    last_rsi = float(rsi_series.iloc[-1])
    last_macd = float(macd_line.iloc[-1])
    last_signal = float(signal_line.iloc[-1])
    composite_signal, composite_note = get_composite_signal(momentum, last_rsi, last_macd, last_signal)

    st.divider()
    col_title, col_add = st.columns([4, 1])
    col_title.subheader(f"{company_name}（{symbol}）｜{market}")

    already_in = any(r["symbol"] == symbol for r in watchlist_rows)
    if not already_in:
        if col_add.button("⭐ 加入自選", key=f"add_{symbol}"):
            ok = db_insert("watchlist", {"symbol": symbol, "name": company_name})
            if ok:
                st.toast(f"{symbol} 已加入自選清單")
                st.rerun()
            else:
                st.error("加入失敗，請看終端機錯誤訊息")
    else:
        col_add.success("已在自選")

    c1, c2 = st.columns(2)
    c1.metric("收盤價", f"{last_close:.2f}")
    c2.metric("ATR（波動度）", f"{last_atr:.2f}")
    c3, c4 = st.columns(2)
    c3.metric("建議停損", f"{stop_loss:.2f}", delta=f"-{last_atr*atr_mult:.2f}", delta_color="inverse")
    c4.metric(f"建議部位（{'張' if lot_size==1000 else '股'}）", f"{lots}")

    # 綜合訊號（最醒目放最上面）
    if "強力買進" in composite_signal:
        st.success(f"### {composite_signal}")
        st.caption(composite_note)
    elif "強力賣出" in composite_signal:
        st.error(f"### {composite_signal}")
        st.caption(composite_note)
    else:
        st.warning(f"### {composite_signal}")
        st.caption(composite_note)

    # 三指標個別狀態
    col_fi, col_rsi, col_macd = st.columns(3)
    col_fi.info(f"**FI 動能**：{momentum}")

    rsi_status = "🔴 超買" if last_rsi > 70 else "🟢 超賣" if last_rsi < 30 else "🟡 中性"
    col_rsi.info(f"**RSI（14）**：{last_rsi:.1f}　{rsi_status}")

    macd_status = "🟢 金叉" if last_macd > last_signal else "🔴 死叉"
    col_macd.info(f"**MACD**：{macd_status}　差距 {last_macd - last_signal:.2f}")

    if "背離" in divergence and "無" not in divergence:
        st.warning(f"**FI 背離訊號**：{divergence}")
    st.info(f"**最大風險**：{actual_risk:,.0f} 元（本金 {risk_pct*100:.0f}%）")

    with st.expander("🔔 設定價格警示"):
        col_p, col_dir, col_btn = st.columns([2, 2, 1])
        target_price = col_p.number_input("目標價", value=float(round(last_close*0.95, 1)), key=f"tp_{symbol}")
        direction = col_dir.selectbox("條件", ["跌破此價格", "突破此價格"], key=f"dir_{symbol}")
        if col_btn.button("設定", key=f"alert_{symbol}"):
            db_insert("alerts", {"symbol": symbol, "name": company_name, "target_price": target_price, "direction": direction})
            st.toast(f"警示已設定：{symbol} {direction} {target_price}")

    fig = make_subplots(rows=5, cols=1, shared_xaxes=True,
                        row_heights=[0.40, 0.15, 0.15, 0.15, 0.15],
                        vertical_spacing=0.02,
                        subplot_titles=("K線 + 停損線", f"Force Index EMA（{fi_period}）", "RSI（14）", "MACD（12/26/9）", "成交量"))

    # K線
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                  name="K線", increasing_line_color="#ef5350", decreasing_line_color="#26a69a"), row=1, col=1)
    fig.add_hline(y=stop_loss, line_dash="dash", line_color="orange", line_width=1.5,
                  annotation_text=f"停損 {stop_loss:.2f}", annotation_position="right", row=1, col=1)

    # 均線
    ma_colors = {5: "#ffd54f", 20: "#42a5f5", 60: "#ef5350"}
    if show_ma:
        ma_data = calc_ma(df["Close"], show_ma)
        for p in show_ma:
            fig.add_trace(go.Scatter(x=ma_data[p].index, y=ma_data[p].values,
                                     line=dict(color=ma_colors.get(p, "#ffffff"), width=1.2),
                                     name=f"MA{p}"), row=1, col=1)

    # 布林通道
    if show_bb:
        bb_upper, bb_mid, bb_lower = calc_bollinger(df["Close"])
        fig.add_trace(go.Scatter(x=bb_upper.index, y=bb_upper.values,
                                  line=dict(color="rgba(100,181,246,0.6)", width=1),
                                  name="BB上軌", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=bb_lower.index, y=bb_lower.values,
                                  fill="tonexty", fillcolor="rgba(100,181,246,0.06)",
                                  line=dict(color="rgba(100,181,246,0.6)", width=1),
                                  name="BB下軌", showlegend=False), row=1, col=1)

    # Force Index EMA
    fi_colors = ["#ef5350" if v >= 0 else "#26a69a" for v in fi_ema]
    fig.add_trace(go.Bar(x=fi_ema.index, y=fi_ema.values, marker_color=fi_colors, name="FI EMA"), row=2, col=1)
    fig.add_hline(y=0, line_color="gray", line_width=0.8, row=2, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=rsi_series.index, y=rsi_series.values, line=dict(color="#ab47bc", width=1.5), name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="#ef5350", line_width=1, row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#26a69a", line_width=1, row=3, col=1)

    # MACD
    hist_colors = ["#ef5350" if v >= 0 else "#26a69a" for v in macd_hist]
    fig.add_trace(go.Bar(x=macd_hist.index, y=macd_hist.values, marker_color=hist_colors, name="MACD Hist"), row=4, col=1)
    fig.add_trace(go.Scatter(x=macd_line.index, y=macd_line.values, line=dict(color="#42a5f5", width=1.2), name="MACD"), row=4, col=1)
    fig.add_trace(go.Scatter(x=signal_line.index, y=signal_line.values, line=dict(color="#ff7043", width=1.2), name="Signal"), row=4, col=1)
    fig.add_hline(y=0, line_color="gray", line_width=0.8, row=4, col=1)

    # 成交量
    vol_colors = ["#ef5350" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#26a69a" for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=vol_colors, name="成交量"), row=5, col=1)
    vol_ma = df["Volume"].rolling(20).mean()
    fig.add_trace(go.Scatter(x=vol_ma.index, y=vol_ma.values,
                              line=dict(color="#ffd54f", width=1.2), name="Vol MA20"), row=5, col=1)

    fig.update_layout(height=900, showlegend=True, xaxis_rangeslider_visible=False,
                      plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#fafafa",
                      hovermode="x",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                                  font=dict(size=11), bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(gridcolor="#2a2a2a",
                     showspikes=True, spikemode="across+toaxis", spikesnap="cursor",
                     spikecolor="rgba(255,255,255,0.25)", spikethickness=1, spikedash="solid")
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
            st.session_state.symbol = symbol
            st.session_state.market = market
            st.session_state.company = company_name
            if db_insert("search_history", {"symbol": symbol, "name": company_name}):
                all_history = db_select("search_history", order_col="searched_at", desc=False, limit=1000)
                if len(all_history) > 20:
                    for h in all_history[:len(all_history)-20]:
                        db_delete("search_history", h["id"])
    elif run:
        st.warning("請輸入股票代號")

    if st.session_state.symbol:
        df = fetch_data(st.session_state.symbol, data_period)
        if df is not None and len(df) >= 30:
            render_analysis(st.session_state.symbol, st.session_state.market, df, st.session_state.company)

with tab_watchlist:
    if not watchlist_rows:
        st.info("自選清單是空的，先查詢股票後點「⭐ 加入自選」。")
    else:
        if st.button("🔄 一鍵掃描所有自選股", type="primary"):
            for row in watchlist_rows:
                sym = row["symbol"]
                mkt = "台股" if sym.endswith(".TW") else "美股"
                with st.spinner(f"分析 {sym}..."):
                    df = fetch_data(sym, data_period)
                if df is not None and len(df) >= 30:
                    render_analysis(sym, mkt, df, row["name"])
                else:
                    st.warning(f"{sym} 資料抓取失敗，跳過")

with tab_alerts:
    alert_rows = db_select("alerts", order_col="created_at", desc=True)
    if not alert_rows:
        st.info("尚無警示，可在查詢結果頁面展開「設定價格警示」新增。")
    else:
        st.write(f"共 {len(alert_rows)} 個警示：")
        for row in alert_rows:
            df_check = fetch_data(row["symbol"], "5d")
            current_price = float(df_check["Close"].iloc[-1]) if df_check is not None else None
            with st.container(border=True):
                col_info, col_del = st.columns([5, 1])
                with col_info:
                    st.write(f"**{row['symbol']}** {row['name']}")
                    st.caption(f"目標：{row['target_price']} ｜ 現價：{current_price:.2f}" if current_price else f"目標：{row['target_price']} ｜ 現價：無法取得")
                    if current_price:
                        triggered = ((row["direction"] == "跌破此價格" and current_price < row["target_price"]) or
                                     (row["direction"] == "突破此價格" and current_price > row["target_price"]))
                        if triggered:
                            st.error(f"🚨 已{row['direction']}！")
                        else:
                            st.success(f"✅ 監控中：{row['direction']}")
                if col_del.button("🗑️", key=f"del_alert_{row['id']}"):
                    db_delete("alerts", row["id"])
                    st.rerun()
