import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# =========================
# CONFIG
# =========================

st.set_page_config(layout="wide")
st.title("APEX PREDATOR TERMINAL")

BOT_TOKEN = "8334346794:AAE133CpkLqeTbuJhwmJcSUVvMlaQE77Lzg"
CHAT_ID = "698628907"

ALERT_FILE = "alerted_symbols.json"

BINANCE_FUTURES = "https://fapi.binance.com"

# =========================
# ALERT STORAGE SAFE LOAD
# =========================

def load_alerts():
    if not os.path.exists(ALERT_FILE):
        return {}
    try:
        with open(ALERT_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_alerts(data):
    with open(ALERT_FILE, "w") as f:
        json.dump(data, f)

alerts = load_alerts()

# =========================
# TELEGRAM ALERT
# =========================

def send_telegram(symbol, score, grade):

    if symbol in alerts:
        return

    msg = (
        f"APEX SIGNAL\n\n"
        f"Symbol: {symbol}\n"
        f"Grade: {grade}\n"
        f"Apex Score: {score:.2f}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": msg
    }

    try:
        requests.post(url, data=payload)
        alerts[symbol] = datetime.utcnow().isoformat()
        save_alerts(alerts)
    except:
        pass

# =========================
# AUTO REFRESH (NO DIMMING)
# =========================

st_autorefresh(interval=15000, key="refresh")

# =========================
# BTC PRICE FROM BINANCE
# =========================

def get_btc():

    try:

        r = requests.get(
            f"{BINANCE_FUTURES}/fapi/v1/ticker/24hr",
            params={"symbol": "BTCUSDT"}
        )

        data = r.json()

        price = float(data["lastPrice"])
        change = float(data["priceChangePercent"])

        return price, change

    except Exception as e:

        st.error(f"BTC error: {e}")
        return None, None

# =========================
# MARKET DATA FROM BINANCE
# =========================

def get_market():

    try:

        r = requests.get(f"{BINANCE_FUTURES}/fapi/v1/ticker/24hr")

        data = r.json()

        rows = []

        for coin in data:

            symbol = coin["symbol"]

            if not symbol.endswith("USDT"):
                continue

            volume = float(coin["quoteVolume"])
            change = float(coin["priceChangePercent"])

            lag_score = volume / (abs(change) + 1)

            rows.append({
                "Symbol": symbol,
                "Change %": change,
                "Volume": volume,
                "Lag Score": lag_score
            })

        df = pd.DataFrame(rows)

        # Apex Score normalization
        df["Apex Score"] = (
            (df["Lag Score"] - df["Lag Score"].min())
            /
            (df["Lag Score"].max() - df["Lag Score"].min())
        ) * 100

        # Grade logic
        def grade(score):

            if score >= 85:
                return "A+"
            elif score >= 70:
                return "A"
            elif score >= 55:
                return "B"
            else:
                return "C"

        df["Grade"] = df["Apex Score"].apply(grade)

        return df.sort_values("Apex Score", ascending=False)

    except Exception as e:

        st.error(f"Market error: {e}")
        return pd.DataFrame()

# =========================
# DISPLAY BTC
# =========================

btc_price, btc_change = get_btc()

if btc_price:

    color = "green" if btc_change > 0 else "red"

    st.markdown(
        f"<h1 style='color:{color}'>BTC ${btc_price:,.0f} ({btc_change:.2f}%)</h1>",
        unsafe_allow_html=True
    )

# =========================
# DISPLAY MARKET
# =========================

df = get_market()

if df.empty:

    st.warning("No market data")

else:

    top = df.head(25)

    st.subheader("Apex Lag Leaderboard")
    st.dataframe(top, use_container_width=True)

    # TELEGRAM ALERT ONLY A+
    for _, row in top.iterrows():

        if row["Grade"] == "A+":
            send_telegram(
                row["Symbol"],
                row["Apex Score"],
                row["Grade"]
            )
