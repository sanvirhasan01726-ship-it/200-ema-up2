import streamlit as st
import ccxt.pro as ccxtpro
import asyncio
import pandas as pd
import pandas_ta as ta
import requests
import threading
import time
from datetime import datetime

# --- TELEGRAM CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "8957518460:AAE_9HaugsNNYfjOzCpbHi2nJAEKf4GSiKs"
TELEGRAM_CHAT_ID = "6166836299"

def send_telegram_message(message):
    """টেলিগ্রামে মেসেজ পাঠানোর ফাংশন"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- STREAMLIT CONFIGURATION ---
st.set_page_config(page_title="24/7 Binance EMA Scanner", layout="wide")

# --- UI DESIGN / LUXURY CUSTOM CSS ---
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #090d16 0%, #111827 100%);
        color: #f8fafc;
    }
    h1 {
        color: #00d2ff !important;
        background: linear-gradient(to right, #00ffff, #0088ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'Inter', sans-serif;
        font-weight: 900 !important;
        text-shadow: 0px 0px 20px rgba(0, 255, 255, 0.3);
    }
    .scanning-box {
        background: rgba(17, 24, 39, 0.85);
        border: 2px solid #38bdf8;
        box-shadow: 0px 0px 25px rgba(56, 189, 248, 0.4);
        padding: 25px;
        border-radius: 16px;
        text-align: center;
        margin: 20px 0;
        animation: pulse 1.5s infinite alternate;
    }
    .scanning-coin {
        font-size: 3rem !important;
        font-weight: 800;
        color: #ff007f !important;
        text-shadow: 0 0 15px rgba(255, 0, 127, 0.6);
        letter-spacing: 2px;
    }
    @keyframes pulse {
        0% { transform: scale(0.99); box-shadow: 0 0 15px rgba(56, 189, 248, 0.3); }
        100% { transform: scale(1.01); box-shadow: 0 0 30px rgba(56, 189, 248, 0.6); }
    }
    div[data-testid="metric-container"] {
        background-color: #111827;
        border: 1px solid #1f2937;
        padding: 20px;
        border-radius: 14px;
    }
    .binance-btn {
        display: inline-block;
        padding: 6px 12px;
        background: linear-gradient(135deg, #f3ba2f 0%, #d49b00 100%);
        color: #000 !important;
        font-weight: bold;
        border-radius: 6px;
        text-decoration: none;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Premium Binance 24/7 Telegram Scanner")
st.write("এটি ব্যাকগ্রাউন্ডে ২৪ ঘণ্টা সচল থাকবে এবং প্রতি ১৫ মিনিট পর পর টেলিগ্রামে সিগন্যাল পাঠাবে।")

# Global State Shared between Background Thread and UI
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = "এখনো স্ক্যান হয়নি"
if 'bullish_coins' not in st.session_state:
    st.session_state.bullish_coins = []
if 'total_scanned' not in st.session_state:
    st.session_state.total_scanned = 0
if 'current_progress' not in st.session_state:
    st.session_state.current_progress = "নিষ্ক্রিয়"

# UI Placeholders
progress_placeholder = st.empty()
metrics_placeholder = st.empty()
table_placeholder = st.empty()

# --- ASYNC CORE OPERATIONS ---

async def fetch_top_350_futures(exchange):
    try:
        markets = await exchange.load_markets()
        futures_pairs = [
            symbol for symbol, market in markets.items()
            if market.get('active') and market.get('linear') and market.get('swap') and market.get('settle') == 'USDT'
        ]
        tickers = await exchange.fetch_tickers(futures_pairs)
        sorted_tickers = sorted(
            tickers.values(), 
            key=lambda x: x.get('quoteVolume', 0) if x.get('quoteVolume') is not None else 0, 
            reverse=True
        )
        return [ticker['symbol'] for ticker in sorted_tickers[:350]]
    except Exception as e:
        print(f"Market fetch error: {e}")
        return []

async def fetch_and_calculate_ema(exchange, symbol):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=250)
        if len(ohlcv) < 200:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ema_200'] = ta.ema(df['close'], length=200)
        
        last_close = df['close'].iloc[-1]
        last_ema = df['ema_200'].iloc[-1]
        
        if not pd.isna(last_ema) and last_close > last_ema:
            return {
                "Symbol": symbol,
                "Price": last_close,
                "200 EMA": round(last_ema, 4),
                "Distance (%)": round(((last_close - last_ema) / last_ema) * 100, 2)
            }
    except Exception:
        pass
    return None

async def scan_process():
    """একক স্ক্যান রান করার ফাংশন"""
    exchange = ccxtpro.binance({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
    symbols_to_scan = await fetch_top_350_futures(exchange)
    
    if not symbols_to_scan:
        await exchange.close()
        return
    
    bullish_list = []
    total_coins = len(symbols_to_scan)
    st.session_state.total_scanned = total_coins
    
    batch_size = 10
    for i in range(0, total_coins, batch_size):
        batch = symbols_to_scan[i:i+batch_size]
        perc = int(((i + len(batch)) / total_coins) * 100)
        
        # UI প্রোগ্রেস মেসেজ আপডেট
        st.session_state.current_progress = f"🔍 স্ক্যানিং: {perc}% ({min(i+batch_size, total_coins)}/{total_coins}) -> {batch[0].split('/')[0]}"
        
        tasks = [fetch_and_calculate_ema(exchange, symbol) for symbol in batch]
        results = await asyncio.gather(*tasks)
        
        for res in results:
            if res:
                bullish_list.append(res)
        await asyncio.sleep(0.2)
        
    await exchange.close()
    
    # স্টেট আপডেট
    st.session_state.bullish_coins = bullish_list
    st.session_state.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.current_progress = "সম্পন্ন (পরবর্তী স্ক্যান ১৫ মিনিট পর)"
    
    # --- টেলিগ্রাম অ্যালার্ট মেসেজ জেনারেশন ---
    if bullish_list:
        tg_msg = f"🔔 *Binance 15M 200 EMA Bullish Report*\n"
        tg_msg += f"⏰ সময়: `{st.session_state.last_scan_time}`\n"
        tg_msg += f"📊 মোট স্ক্যান: `{total_coins}` | বুলিশ কয়েন: `{len(bullish_list)}`\n\n"
        tg_msg += "*কয়েন লিস্ট (Price / Distance):*\n"
        
        # টেলিগ্রামে প্রথম ২০টি কয়েন পাঠানো হচ্ছে যাতে মেসেজ ওভারফ্লো না হয়
        for coin in bullish_list[:20]:
            clean_name = coin['Symbol'].split(':')[0]
            tg_msg += f"• `{clean_name}`: ${coin['Price']} (+{coin['Distance (%)']}% Above EMA)\n"
        
        if len(bullish_list) > 20:
            tg_msg += f"\n_...এবং আরও {len(bullish_list)-20}টি কয়েন আছে। বিস্তারিত ওয়েব ড্যাশবোর্ডে দেখুন।_"
    else:
        tg_msg = f"ℹ️ *Binance 15M 200 EMA Scan Completed*\n"
        tg_msg += f"⏰ সময়: `{st.session_state.last_scan_time}`\n"
        tg_msg += "এই মুহূর্তে কোনো কয়েন ২০০ EMA এর উপরে পাওয়া যায়নি।"
        
    send_telegram_message(tg_msg)

def start_background_loop():
    """২৪ ঘণ্টা ব্যাকগ্রাউন্ডে রান রাখার জন্য ইনফিনিটি লুপ"""
    while True:
        try:
            asyncio.run(scan_process())
        except Exception as e:
            print(f"Background Loop Error: {e}")
        time.sleep(900) # ঠিক ১৫ মিনিট (৯০০ সেকেন্ড) পর পর রান হবে

# অ্যাপ চালু হওয়ার সময় ব্যাকগ্রাউন্ড থ্রেড একবারই স্টার্ট করবে
if 'thread_started' not in st.session_state:
    st.session_state.thread_started = True
    bg_thread = threading.Thread(target=start_background_loop, daemon=True)
    bg_thread.start()

# --- UI রেন্ডারিং (অটো রিফ্রেশ হবে যখনই ইউজার পেজ ভিজিট করবে) ---

if "🔍 স্ক্যানিং" in st.session_state.current_progress:
    progress_placeholder.markdown(f"""
        <div class="scanning-box">
            <p style="color: #38bdf8; font-size: 1.2rem; margin-bottom: 5px; font-weight: 600;">
                {st.session_state.current_progress}
            </p>
            <div class="scanning-coin">SCANNING</div>
        </div>
    """, unsafe_allow_html=True)
else:
    progress_placeholder.info(f"🟢 স্ট্যাটাস: {st.session_state.current_progress}")

with metrics_placeholder.container():
    col1, col2, col3 = st.columns(3)
    col1.metric("মোট স্ক্যান করা কয়েন", st.session_state.total_scanned)
    col2.metric("200 EMA-এর উপরে বুলিশ", len(st.session_state.bullish_coins))
    col3.metric("সর্বশেষ আপডেট সময়", st.session_state.last_scan_time)

if st.session_state.bullish_coins:
    df_result = pd.DataFrame(st.session_state.bullish_coins)
    
    def make_binance_link(symbol):
        clean_symbol = symbol.split(':')[0].replace('/', '')
        url = f"https://www.binance.com/en/futures/{clean_symbol}"
        return f'<a href="{url}" target="_blank" class="binance-btn">🔗 Trade on Binance</a>'
    
    df_result['Action'] = df_result['Symbol'].apply(make_binance_link)
    table_html = df_result.to_html(escape=False, index=False, classes='table table-dark')
    
    with table_placeholder.container():
        st.markdown("### 📈 লাইভ বুলিশ কয়েন লিস্ট")
        st.markdown(table_html, unsafe_allow_html=True)
else:
    table_placeholder.warning("এখনো কোনো বুলিশ কয়েন ডাটাবেজে নেই বা স্ক্যান সম্পন্ন হয়নি।")

# ওয়েব ইউজারদের জন্য ম্যানুয়াল রিফ্রেশ বাটন
if st.button("🔄 ড্যাশবোর্ড ডাটা রিফ্রেশ করুন"):
    st.rerun()