import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
st.title("APEX PREDATOR TERMINAL")

BOT_TOKEN = "8334346794:AAE133CpkLqeTbuJhwmJcSUVvMlaQE77Lzg"
CHAT_ID = "698628907"

ALERT_FILE = "alerted_symbols.json"

def load_alerts():
    if not os.path.exists(ALERT_FILE):
        return {}
    try:
        with open(ALERT_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_alerts(alerts):
    with open(ALERT_FILE, "w") as f:
        json.dump(alerts, f)

alerts = load_alerts()

def send_telegram(symbol, score):
    if symbol in alerts:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    msg = f"APEX SIGNAL\nSymbol: {symbol}\nScore: {score}"

    payload = {"chat_id": CHAT_ID, "text": msg}

    try:
        requests.post(url, data=payload)
        alerts[symbol] = datetime.utcnow().isoformat()
        save_alerts(alerts)
    except:
        pass

st_autorefresh(interval=15000, key="refresh")

# USE COINCAP FOR BTC (WORKS ON CLOUD)

def get_btc():
    try:
        r = requests.get("https://api.coincap.io/v2/assets/bitcoin")
        data = r.json()["data"]

        price = float(data["priceUsd"])
        change = float(data["changePercent24Hr"])

        return price, change

    except Exception as e:
        st.error(f"BTC fetch error: {e}")
        return None, None

# USE COINGECKO FOR MARKET DATA (WORKS ON CLOUD)

def get_market():

    try:

        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 250,
                "page": 1
            }
        )

        data = r.json()

        rows = []

        for coin in data:

            symbol = coin["symbol"].upper()
            change = coin["price_change_percentage_24h"]
            volume = coin["total_volume"]

            lag_score = volume / (abs(change) + 1)

            rows.append({
                "Symbol": symbol,
                "Change %": round(change, 2),
                "Volume": volume,
                "Lag Score": lag_score
            })

        df = pd.DataFrame(rows)

        df["Apex Score"] = (
            (df["Lag Score"] - df["Lag Score"].min())
            / (df["Lag Score"].max() - df["Lag Score"].min())
        ) * 100

        df["Grade"] = df["Apex Score"].apply(
            lambda x: "A+" if x >= 80 else "A" if x >= 60 else "B"
        )

        return df.sort_values("Apex Score", ascending=False)

    except Exception as e:

        st.error(f"Market fetch error: {e}")
        return pd.DataFrame()

btc_price, btc_change = get_btc()

if btc_price:

    color = "green" if btc_change > 0 else "red"

    st.markdown(
        f"<h1 style='color:{color}'>BTC ${btc_price:,.0f} ({btc_change:.2f}%)</h1>",
        unsafe_allow_html=True
    )

df = get_market()

if not df.empty:

    top = df.head(10)

    st.subheader("Top Apex Opportunities")
    st.dataframe(top)

    for _, row in top.iterrows():

        if row["Grade"] == "A+":
            send_telegram(row["Symbol"], row["Apex Score"])

else:

    st.warning("Market data unavailable")
