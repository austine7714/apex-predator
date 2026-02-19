import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ============================================
# CONFIG
# ============================================

BOT_TOKEN = "8334346794:AAE133CpkLqeTbuJhwmJcSUVvMlaQE77Lzg"
CHAT_ID = "698628907"

ALERT_FILE = "alerted_symbols.json"
ALERT_BATCH_KEY = "LAST_BATCH_ALERT"
ALERT_COOLDOWN_MINUTES = 60

BYBIT_TICKER = "https://api.bybit.com/v5/market/tickers?category=linear"
BTC_ENDPOINT = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"

# ============================================
# PAGE SETUP
# ============================================

st.set_page_config(layout="wide")

st_autorefresh(interval=10000, key="apex_refresh")

# ============================================
# SAFE ALERT STORAGE
# ============================================

def load_alerts():

    if not os.path.exists(ALERT_FILE):
        return {}

    try:

        with open(ALERT_FILE, "r") as f:

            content = f.read().strip()

            if content == "":
                return {}

            return json.loads(content)

    except:

        return {}

def save_alerts(alerts):

    try:

        with open(ALERT_FILE, "w") as f:

            json.dump(alerts, f)

    except:
        pass

alert_history = load_alerts()

# ============================================
# TELEGRAM BATCH ALERT
# ============================================

def send_hourly_batch_alert(df, bias, regime):

    now = datetime.now()

    last = alert_history.get(ALERT_BATCH_KEY)

    if last:

        last_time = datetime.fromisoformat(last)

        if now - last_time < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
            return

    longs = df[df["Direction"] == "LONG"]
    shorts = df[df["Direction"] == "SHORT"]

    longs = longs[longs["Grade"].isin(["A+", "A"])].head(5)
    shorts = shorts[shorts["Grade"].isin(["A+", "A"])].head(5)

    message = f"APEX HOURLY REPORT\n\nRegime: {regime}\nExecution Bias: {bias}\n\n"

    if not longs.empty:

        message += "LONG SETUPS:\n"

        for _, row in longs.iterrows():

            message += f"{row['Symbol']} | {row['Grade']} | Intent {row['Apex Intent Score']}\n"

    if not shorts.empty:

        message += "\nSHORT SETUPS:\n"

        for _, row in shorts.iterrows():

            message += f"{row['Symbol']} | {row['Grade']} | Intent {row['Apex Intent Score']}\n"

    try:

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )

        alert_history[ALERT_BATCH_KEY] = now.isoformat()
        save_alerts(alert_history)

    except:
        pass

# ============================================
# BTC FETCH
# ============================================

def get_btc():

    try:

        r = requests.get(BTC_ENDPOINT, timeout=10)

        data = r.json()["result"]["list"][0]

        price = float(data["lastPrice"])
        change = float(data["price24hPcnt"]) * 100

        return price, change

    except:

        return None, None

# ============================================
# BTC REGIME DETECTION
# ============================================

def detect_regime(change):

    strength = min(abs(change) * 30, 100)

    if change > 2:

        regime = "EARLY EXPANSION"
        explanation = "Strong bullish propagation phase."
        bias = "LONG"

    elif change < -1:

        regime = "EARLY DISTRIBUTION"
        explanation = "Strong bearish propagation phase."
        bias = "SHORT"

    else:

        regime = "PROPAGATION"
        explanation = "Neutral propagation phase."
        bias = "LONG"

    return regime, explanation, strength, bias

# ============================================
# PROPAGATION METER
# ============================================

def propagation_meter(df, strength):

    if df.empty:
        return 0

    aligned = df[df["Grade"] == "A+"]

    score = len(aligned) * 10 + strength

    return min(100, score)

# ============================================
# MARKET FETCH
# ============================================

def fetch_market():

    try:

        r = requests.get(BYBIT_TICKER, timeout=10)

        tickers = r.json()["result"]["list"]

        rows = []

        for coin in tickers:

            symbol = coin["symbol"]

            change = float(coin["price24hPcnt"]) * 100

            oi = float(coin["openInterest"])

            volume = float(coin["turnover24h"])

            lag = oi / (abs(change) + 1)

            rows.append({

                "Symbol": symbol,
                "Price Change %": round(change, 2),
                "Open Interest": oi,
                "Volume": volume,
                "Lag Score": lag

            })

        return pd.DataFrame(rows)

    except:

        return pd.DataFrame()

# ============================================
# PROCESS DATA
# ============================================

def process(df, btc_change, strength):

    if df.empty:
        return df

    df["Apex Score"] = (
        (df["Lag Score"] - df["Lag Score"].min())
        /
        (df["Lag Score"].max() - df["Lag Score"].min())
    ) * 100

    df["Apex Score"] = df["Apex Score"].round(1)

    def grade(score):

        if score >= 80:
            return "A+"
        elif score >= 60:
            return "A"
        elif score >= 40:
            return "B"
        else:
            return ""

    df["Grade"] = df["Apex Score"].apply(grade)

    def direction(change):

        if btc_change > 0 and change >= 0:
            return "LONG"

        if btc_change < 0 and change <= 0:
            return "SHORT"

        return "MISALIGNED"

    df["Direction"] = df["Price Change %"].apply(direction)

    df["Apex Intent Score"] = (
        df["Apex Score"] + strength * 0.2
    ).clip(upper=100).round(1)

    df = df[df["Grade"] != ""]

    df = df.sort_values("Apex Score", ascending=False)

    return df

# ============================================
# MAIN DISPLAY
# ============================================

st.title("APEX PREDATOR TERMINAL")

btc_price, btc_change = get_btc()

if btc_price:

    regime, explanation, strength, bias = detect_regime(btc_change)

    color = "#00ff88" if btc_change >= 0 else "#ff4b4b"

    st.markdown(
        f"<h1 style='color:{color};'>BTC ${btc_price:,.0f} ({btc_change:.2f}%)</h1>",
        unsafe_allow_html=True
    )

    banner = "#00ff88" if bias == "LONG" else "#ff4b4b"

    st.markdown(
        f"<div style='background:{banner};padding:15px;border-radius:10px;text-align:center;font-size:24px;font-weight:bold;'>EXECUTION BIAS: {bias}</div>",
        unsafe_allow_html=True
    )

    st.markdown(f"### {regime}")
    st.markdown(explanation)

else:

    strength = 50
    bias = "LONG"
    regime = "UNKNOWN"
    btc_change = 0

df = fetch_market()

df = process(df, btc_change, strength)

# ============================================
# PROPAGATION STRENGTH BAR
# ============================================

prop_strength = propagation_meter(df, strength)

st.markdown("### PROPAGATION STRENGTH")

st.progress(prop_strength / 100)

st.write(f"{prop_strength}/100")

# ============================================
# TABLES
# ============================================

longs = df[df["Direction"] == "LONG"]
shorts = df[df["Direction"] == "SHORT"]

if bias == "LONG":

    st.markdown("## LONG SETUPS (EXECUTION PRIORITY)")
    st.dataframe(longs, use_container_width=True)

    st.divider()

    st.markdown("## SHORT SETUPS")
    st.dataframe(shorts, use_container_width=True)

else:

    st.markdown("## SHORT SETUPS (EXECUTION PRIORITY)")
    st.dataframe(shorts, use_container_width=True)

    st.divider()

    st.markdown("## LONG SETUPS")
    st.dataframe(longs, use_container_width=True)

# ============================================
# TELEGRAM ALERT
# ============================================

send_hourly_batch_alert(df, bias, regime)
