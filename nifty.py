Samajh gaya — sab features ek saath add kar raha hoon. Poora naya file likh raha hoon:

**Syntax check passed ✅ — Download karo aur replace karo.**

---

## Kya Kya Add/Fix Kiya

**🔧 Errors Fixed:**
- `.applymap()` completely hataya — sirf `.map()` use hota hai ab (pandas 2.1+ safe)
- Syntax verify kiya — zero errors

**📲 Telegram Alerts:**
- STRONG BUY / STRONG SELL pe automatically message bhejta hai
- **15 min cooldown** — same stock ka baar baar alert nahi aayega
- Sidebar mein toggle ON/OFF kar sakte ho
- Secrets mein add karo:
```toml
TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID   = "your_chat_id"
```

**📊 3 Naye Indicators:**
- **HTF Trend** — 15-min chart pe EMA20/50 se trend (double weight = 2 points)
- **Relative Strength** — Stock vs Nifty comparison (last 10 candles)
- **ORB** — Opening Range Breakout/Breakdown (first 3 candles)

**⚪ SIDEWAYS Detection** — ATR volatility < 0.3% hone pe automatically "SIDEWAYS" signal — choppy market mein trade nahi karega

**Scoring ab 0–14 range** mein hai — threshold 6+ Strong Buy / -6 Strong Sell
