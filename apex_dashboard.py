import streamlit as st
import requests
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ============================
# TELEGRAM SETTINGS
# ============================

BOT_TOKEN = "8334346794:AAE133CpkLqeTbuJhwmJcSUVvMlaQE77Lzg"
CHAT_ID = "698628907"

ALERT_FILE = "alerted_symbols.json"

ALERT_COOLDOWN_HOURS = 4

# ============================
# SAFE JSON LOAD (PERMANENT FIX)
# ============================

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

# ============================
# TELEGRAM SEND WITH LOCK
# ============================

def send_telegram_once(symbol, message):

    now = datetime.now()

    last_alert = alert_history.get(symbol)

    if last_alert:

        last_time = datetime.fromisoformat(last_alert)

        if now - last_time < timedelta(hours=ALERT_COOLDOWN_HOURS):
            return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(url, data=payload, timeout=10)

        if response.status_code == 200:

            alert_history[symbol] = now.isoformat()
            save_alerts(alert_history)

            return True

    except:
        pass

    return False


# ============================
# AUTO REFRESH (NO FLICKER)
# ============================

st_autorefresh(interval=5000, key="apexrefresh")

st.set_page_config(layout="wide")

# ============================
# API ENDPOINTS
# ============================

BYBIT_URL = "https://api.bytick.com/v5/market/tickers?category=linear"
BTC_URL = "https://api.bytick.com/v5/market/tickers?category=linear&symbol=BTCUSDT"

# ============================
# SESSION STATE LOCK
# ============================

if "startup_sent" not in st.session_state:

    send_telegram_once(
        "SYSTEM_START",
        "APEX TERMINAL ULTRA MODE CONNECTED"
    )

    st.session_state.startup_sent = True


if "lag_history" not in st.session_state:
    st.session_state.lag_history = {}

if "oi_history" not in st.session_state:
    st.session_state.oi_history = {}

# ============================
# BTC FUNCTIONS
# ============================

def get_btc():

    try:

        r = requests.get(BTC_URL, timeout=10)
        data = r.json()["result"]["list"][0]

        price = float(data["lastPrice"])
        change = float(data["price24hPcnt"]) * 100

        return price, change

    except:

        return None, None


def detect_btc_regime(change):

    strength = min(100, abs(change) * 30)

    if change > 2:

        regime = "EARLY EXPANSION"
        explanation = "Long propagation favored"
        bias = "LONG"

    elif -1 <= change <= 2:

        regime = "PROPAGATION"
        explanation = "Best propagation phase"
        bias = "LONG"

    else:

        regime = "EARLY DISTRIBUTION"
        explanation = "Short propagation favored"
        bias = "SHORT"

    return regime, explanation, strength, bias


# ============================
# APEX CALCULATIONS
# ============================

def lag_score(oi, change):

    return oi / (abs(change) + 1)


def normalize(df):

    max_val = df["Lag Score"].max()
    min_val = df["Lag Score"].min()

    df["Apex Score"] = (
        (df["Lag Score"] - min_val) /
        (max_val - min_val)
    ) * 100

    df["Apex Score"] = df["Apex Score"].fillna(50).round(1)

    return df


def grade(score):

    if score >= 80:
        return "A+"
    elif score >= 60:
        return "A"
    elif score >= 40:
        return "B"
    else:
        return ""


def alignment(change, btc_change):

    if btc_change > 0 and change >= 0:
        return "LONG"

    if btc_change < 0 and change <= 0:
        return "SHORT"

    return "MISALIGNED"


def propagation_prob(score, align, strength, oi_accel):

    value = score

    if align != "MISALIGNED":
        value += 10

    if oi_accel > 0:
        value += 5

    value += strength * 0.2

    return min(100, round(value, 1))


# ============================
# MARKET DATA
# ============================

def get_data(btc_change, regime, strength, bias):

    try:

        r = requests.get(BYBIT_URL, timeout=10)
        tickers = r.json()["result"]["list"]

    except:

        return pd.DataFrame()

    rows = []
    now = datetime.now()

    for t in tickers:

        try:

            symbol = t["symbol"]
            oi = float(t["openInterest"])
            change = float(t["price24hPcnt"]) * 100

            lag = lag_score(oi, change)

            if symbol not in st.session_state.lag_history:
                st.session_state.lag_history[symbol] = now

            lag_time = (
                now - st.session_state.lag_history[symbol]
            ).seconds / 60

            prev_oi = st.session_state.oi_history.get(symbol, oi)

            oi_accel = (
                ((oi - prev_oi) / prev_oi) * 100
                if prev_oi else 0
            )

            st.session_state.oi_history[symbol] = oi

            rows.append({

                "Symbol": symbol,
                "Price Change %": round(change, 2),
                "Lag Score": lag,
                "Lag Persistence": round(lag_time, 1),
                "OI Accel %": round(oi_accel, 2)

            })

        except:
            continue

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = normalize(df)

    df["Grade"] = df["Apex Score"].apply(grade)

    df["Direction"] = df["Price Change %"].apply(
        lambda x: alignment(x, btc_change)
    )

    df["Apex Intent Score"] = df.apply(
        lambda row: propagation_prob(
            row["Apex Score"],
            row["Direction"],
            strength,
            row["OI Accel %"]
        ),
        axis=1
    )

    df = df[df["Grade"] != ""]

    df = df.sort_values("Apex Score", ascending=False)

    # ============================
    # ULTRA PRECISION ALERT (SAFE)
    # ============================

    for _, row in df.iterrows():

        symbol = row["Symbol"]

        if not (
            row["Grade"] == "A+"
            and row["Apex Intent Score"] >= 95
            and row["Direction"] == bias
            and row["OI Accel %"] > 0
        ):
            continue

        message = f"""
ULTRA APEX SIGNAL

Symbol: {symbol}
Grade: {row['Grade']}
Intent Score: {row['Apex Intent Score']}
Direction: {row['Direction']}
Regime: {regime}
OI Accel: {row['OI Accel %']}%

Highest probability propagation setup detected.
"""

        send_telegram_once(symbol, message)

    return df


# ============================
# DISPLAY
# ============================

btc_price, btc_change = get_btc()

if btc_price:

    regime, explanation, strength, bias = detect_btc_regime(btc_change)

    color = "#00ff88" if btc_change >= 0 else "#ff4b4b"

    st.markdown(
        f"<h1 style='color:{color}'>BTC ${btc_price:,.0f} ({btc_change:.2f}%)</h1>",
        unsafe_allow_html=True
    )

    st.markdown(f"### {regime}")
    st.markdown(explanation)

    banner_color = "#00ff88" if bias == "LONG" else "#ff4b4b"

    st.markdown(
        f"<div style='background:{banner_color};padding:12px;border-radius:10px;font-size:22px;font-weight:bold;text-align:center;'>EXECUTION BIAS: {bias}</div>",
        unsafe_allow_html=True
    )

else:

    btc_change = 0
    regime = "UNKNOWN"
    strength = 50
    bias = "LONG"


df = get_data(btc_change, regime, strength, bias)

if not df.empty:

    primary = df[df["Direction"] == bias].head(10)
    secondary = df[df["Direction"] != bias].head(10)

    st.subheader("PRIMARY")
    st.dataframe(primary, use_container_width=True)

    st.divider()

    st.subheader("SECONDARY")
    st.dataframe(secondary, use_container_width=True)
