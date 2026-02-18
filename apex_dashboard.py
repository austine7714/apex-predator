import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ============================================
# BASIC UI INIT (always render something)
# ============================================

st.set_page_config(layout="wide")
st.title("APEX PREDATOR TERMINAL")

# ============================================
# TELEGRAM SETTINGS
# ============================================

BOT_TOKEN = "8334346794:AAE133CpkLqeTbuJhwmJcSUVvMlaQE77Lzg"
CHAT_ID = "698628907"

ALERT_FILE = "alerted_symbols.json"
ALERT_COOLDOWN_HOURS = 4

# ============================================
# SAFE JSON LOAD
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
# TELEGRAM ALERT FUNCTION
# ============================================

def send_telegram_once(symbol, message):

    now = datetime.utcnow()

    last = alert_history.get(symbol)

    if last:
        last_time = datetime.fromisoformat(last)
        if now - last_time < timedelta(hours=ALERT_COOLDOWN_HOURS):
            return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            alert_history[symbol] = now.isoformat()
            save_alerts(alert_history)
    except:
        pass

# ============================================
# AUTO REFRESH
# ============================================

st_autorefresh(interval=10000, key="refresh")

# ============================================
# BYBIT ENDPOINTS (Cloud-safe)
# ============================================

BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
BTC_URL = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"

# ============================================
# BTC FETCH
# ============================================

def get_btc():

    try:
        r = requests.get(BTC_URL, timeout=10)
        data = r.json()

        if "result" not in data:
            return None, None

        btc = data["result"]["list"][0]

        price = float(btc["lastPrice"])
        change = float(btc["price24hPcnt"]) * 100

        return price, change

    except Exception as e:
        st.error(f"BTC fetch error: {e}")
        return None, None

# ============================================
# REGIME DETECTION
# ============================================

def detect_regime(change):

    strength = min(abs(change) * 30, 100)

    if change > 2:
        return "EARLY EXPANSION", "LONG", strength

    elif change < -1:
        return "EARLY DISTRIBUTION", "SHORT", strength

    else:
        return "PROPAGATION", "LONG", strength

# ============================================
# DATA FETCH
# ============================================

def get_market():

    try:

        r = requests.get(BYBIT_URL, timeout=15)
        data = r.json()

        if "result" not in data:
            st.warning("No market data returned")
            return pd.DataFrame()

        tickers = data["result"]["list"]

        rows = []

        for t in tickers:

            try:

                symbol = t["symbol"]
                change = float(t["price24hPcnt"]) * 100
                oi = float(t["openInterest"])

                lag_score = oi / (abs(change) + 1)

                rows.append({

                    "Symbol": symbol,
                    "Change %": round(change, 2),
                    "Open Interest": oi,
                    "Lag Score": lag_score

                })

            except:
                continue

        df = pd.DataFrame(rows)

        if df.empty:
            return df

        # Normalize score
        df["Apex Score"] = (
            (df["Lag Score"] - df["Lag Score"].min())
            / (df["Lag Score"].max() - df["Lag Score"].min())
        ) * 100

        df["Apex Score"] = df["Apex Score"].round(1)

        # Grade
        df["Grade"] = df["Apex Score"].apply(
            lambda x: "A+" if x >= 80 else
                      "A" if x >= 60 else
                      "B"
        )

        return df.sort_values("Apex Score", ascending=False)

    except Exception as e:

        st.error(f"Market fetch error: {e}")
        return pd.DataFrame()

# ============================================
# MAIN EXECUTION
# ============================================

btc_price, btc_change = get_btc()

if btc_price is not None:

    regime, bias, strength = detect_regime(btc_change)

    color = "green" if btc_change > 0 else "red"

    st.markdown(
        f"<h1 style='color:{color}'>BTC ${btc_price:,.0f} ({btc_change:.2f}%)</h1>",
        unsafe_allow_html=True
    )

    st.subheader(f"Regime: {regime} ({bias} favored)")

else:

    st.warning("BTC data unavailable")

df = get_market()

if not df.empty:

    primary = df[df["Grade"] == "A+"].head(10)
    secondary = df[df["Grade"] != "A+"].head(10)

    if bias == "LONG":

        st.subheader("Lagging LONG opportunities")
        st.dataframe(primary)

        st.subheader("Secondary setups")
        st.dataframe(secondary)

    else:

        st.subheader("Lagging SHORT opportunities")
        st.dataframe(primary)

        st.subheader("Secondary setups")
        st.dataframe(secondary)

    # TELEGRAM ALERTS

    for _, row in primary.iterrows():

        if row["Grade"] == "A+" and row["Apex Score"] >= 90:

            send_telegram_once(
                row["Symbol"],
                f"APEX SIGNAL\nSymbol: {row['Symbol']}\nGrade: {row['Grade']}\nScore: {row['Apex Score']}"
            )

else:

    st.warning("Market data empty")
