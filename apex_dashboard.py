import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ============================
# CONFIG
# ============================

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "698628907"

ALERT_FILE = "alert_history.json"
ALERT_INTERVAL_HOURS = 1

BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
BTC_URL = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"

# ============================
# PAGE CONFIG
# ============================

st.set_page_config(layout="wide")
st_autorefresh(interval=60000, key="refresh")

# ============================
# SAFE STORAGE
# ============================

def load_alerts():
    if not os.path.exists(ALERT_FILE):
        return {}
    try:
        with open(ALERT_FILE,"r") as f:
            content=f.read().strip()
            if content=="":
                return {}
            return json.loads(content)
    except:
        return {}

def save_alerts(data):
    try:
        with open(ALERT_FILE,"w") as f:
            json.dump(data,f)
    except:
        pass

alert_history=load_alerts()

# ============================
# TELEGRAM
# ============================

def send_telegram(message):
    try:
        url=f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload={"chat_id":CHAT_ID,"text":message}
        requests.post(url,data=payload,timeout=10)
    except:
        pass

def hourly_report(df_long,df_short,bias):
    now=datetime.now()
    last=alert_history.get("last_hourly")

    if last:
        last=datetime.fromisoformat(last)
        if now-last<timedelta(hours=ALERT_INTERVAL_HOURS):
            return

    message="APEX HOURLY REPORT\n\n"
    message+=f"Execution Bias: {bias}\n\n"

    message+="LONG SETUPS:\n"
    for _,row in df_long.head(5).iterrows():
        message+=(
            f"{row['Symbol']} | Grade {row['Grade']} | "
            f"Entry {row['Entry Signal']} | "
            f"Apex {row['Apex Score']}%\n"
        )

    message+="\nSHORT SETUPS:\n"
    for _,row in df_short.head(5).iterrows():
        message+=(
            f"{row['Symbol']} | Grade {row['Grade']} | "
            f"Entry {row['Entry Signal']} | "
            f"Apex {row['Apex Score']}%\n"
        )

    send_telegram(message)

    alert_history["last_hourly"]=now.isoformat()
    save_alerts(alert_history)

# ============================
# BTC DATA
# ============================

def get_btc():
    try:
        r=requests.get(BTC_URL,timeout=10)
        data=r.json()["result"]["list"][0]
        price=float(data["lastPrice"])
        change=float(data["price24hPcnt"])*100
        return price,change
    except:
        return None,0

def btc_regime(change):

    strength=min(100,abs(change)*30)

    if change>2:
        regime="EARLY EXPANSION"
        bias="LONG"
        explanation="Bullish expansion phase"

    elif change>=-1:
        regime="PROPAGATION"
        bias="LONG"
        explanation="Lag propagation phase"

    else:
        regime="EARLY DISTRIBUTION"
        bias="SHORT"
        explanation="Bearish distribution phase"

    return regime,bias,strength,explanation

# ============================
# NORMALIZATION
# ============================

def normalize(series):
    return ((series-series.min())/(series.max()-series.min()))*100

# ============================
# FOOTPRINT SIGNAL LABELS
# ============================

def absorption_signal(x):
    if x>75: return "INSTITUTIONAL ACCUMULATION"
    elif x>50: return "MODERATE ACCUMULATION"
    else: return "WEAK ACCUMULATION"

def trap_signal(x):
    if x>75: return "TRADERS TRAPPED"
    elif x>50: return "TRAP BUILDING"
    else: return "NO MAJOR TRAP"

def aggression_signal(x):
    if x>75: return "STRONG BUY/SELL PRESSURE"
    elif x>50: return "MODERATE PRESSURE"
    else: return "LOW PRESSURE"

def propagation_signal(x):
    if x>75: return "EXPANSION IMMINENT"
    elif x>50: return "PROPAGATION BUILDING"
    else: return "WEAK PROPAGATION"

# ============================
# ENTRY TIMING ENGINE
# ============================

def entry_score(row, btc_strength):

    score = (
        row["Apex Score"] * 0.35 +
        row["Propagation Acceleration %"] * 0.35 +
        row["Absorption %"] * 0.15 +
        btc_strength * 0.15
    )

    return round(score, 1)


def entry_label(score):

    if score >= 80:
        return "ENTER NOW"

    elif score >= 65:
        return "PREPARE"

    elif score >= 50:
        return "WAIT"

    elif score >= 35:
        return "TOO LATE"

    else:
        return "AVOID"


def entry_explanation(score):

    if score >= 80:
        return "Propagation beginning. Highest probability entry window."

    elif score >= 65:
        return "Accumulation detected. Entry likely soon."

    elif score >= 50:
        return "Setup forming but propagation not confirmed."

    elif score >= 35:
        return "Move already underway. Risk increasing."

    else:
        return "Weak propagation conditions."

# ============================
# MARKET DATA ENGINE
# ============================

def get_market(btc_strength):

    try:
        r=requests.get(BYBIT_URL,timeout=10)
        tickers=r.json()["result"]["list"]
    except:
        return pd.DataFrame()

    rows=[]

    for t in tickers:

        try:

            symbol=t["symbol"]
            change=float(t["price24hPcnt"])*100
            oi=float(t["openInterest"])
            volume=float(t["volume24h"])

            rows.append({
                "Symbol":symbol,
                "Price Change %":round(change,2),
                "Lag Raw":oi/(abs(change)+1),
                "Absorption Raw":oi/(volume+1),
                "Trap Raw":abs(change)*oi,
                "Aggression Raw":volume/(oi+1)
            })

        except:
            continue

    df=pd.DataFrame(rows)

    if df.empty:
        return df

    # Normalize
    df["Apex Score"]=normalize(df["Lag Raw"]).round(1)
    df["Absorption %"]=normalize(df["Absorption Raw"]).round(1)
    df["Trap Probability %"]=normalize(df["Trap Raw"]).round(1)
    df["Aggression %"]=normalize(df["Aggression Raw"]).round(1)

    # Propagation Acceleration
    df["Propagation Acceleration %"]=(
        df["Apex Score"]*0.4+
        df["Absorption %"]*0.2+
        df["Trap Probability %"]*0.2+
        df["Aggression %"]*0.2
    ).round(1)

    # Entry Timing
    df["Entry Timing %"]=df.apply(
        lambda row: entry_score(row, btc_strength),
        axis=1
    )

    df["Entry Signal"]=df["Entry Timing %"].apply(entry_label)
    df["Entry Explanation"]=df["Entry Timing %"].apply(entry_explanation)

    # Signals
    df["Absorption Signal"]=df["Absorption %"].apply(absorption_signal)
    df["Trap Signal"]=df["Trap Probability %"].apply(trap_signal)
    df["Aggression Signal"]=df["Aggression %"].apply(aggression_signal)
    df["Propagation Signal"]=df["Propagation Acceleration %"].apply(propagation_signal)

    # Grade
    df["Grade"]=df["Apex Score"].apply(
        lambda x:"A+" if x>=80 else "A" if x>=60 else "B" if x>=40 else ""
    )

    return df[df["Grade"]!=""].sort_values("Entry Timing %",ascending=False)

# ============================
# EXPLANATION ENGINE
# ============================

def explain(row,bias):

    return f"""
{row['Symbol']}

Grade: {row['Grade']}
Apex Score: {row['Apex Score']}%

Propagation Acceleration: {row['Propagation Acceleration %']}%
{row['Propagation Signal']}

Entry Timing: {row['Entry Timing %']}%
Signal: {row['Entry Signal']}

{row['Entry Explanation']}

Expected Direction: {bias}
"""

# ============================
# UI
# ============================

btc_price,btc_change=get_btc()

regime,bias,strength,regime_explain=btc_regime(btc_change)

color="#00ff88" if bias=="LONG" else "#ff4b4b"

st.title("APEX PREDATOR TERMINAL")

st.markdown(f"# BTC ${btc_price:,.0f} ({btc_change:.2f}%)")

st.markdown(
f"<div style='background:{color};padding:15px;border-radius:10px;text-align:center;font-size:25px;font-weight:bold'>EXECUTION BIAS: {bias}</div>",
unsafe_allow_html=True
)

st.progress(strength/100)
st.write(f"Propagation strength: {strength}%")

df=get_market(strength)

long_df=df[df["Price Change %"]>=0]
short_df=df[df["Price Change %"]<0]

hourly_report(long_df,short_df,bias)

tab1,tab2,tab3=st.tabs(["LONG SETUPS","SHORT SETUPS","EXPLANATIONS"])

with tab1:
    st.dataframe(
        long_df[
            [
                "Symbol",
                "Grade",
                "Apex Score",
                "Propagation Acceleration %",
                "Entry Timing %",
                "Entry Signal"
            ]
        ],
        use_container_width=True
    )

with tab2:
    st.dataframe(
        short_df[
            [
                "Symbol",
                "Grade",
                "Apex Score",
                "Propagation Acceleration %",
                "Entry Timing %",
                "Entry Signal"
            ]
        ],
        use_container_width=True
    )

with tab3:
    for _,row in df.head(15).iterrows():
        st.text(explain(row,bias))
