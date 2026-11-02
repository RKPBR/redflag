# BUILD LOG (resume from here, do not restart)
# Step 1 DONE: type share name -> Yahoo (NSE .NS then .BO) -> price, last 4 quarters, auto red flags.
# Step 1b DONE: his loca.lt tunnel blocks lazy-loaded widgets, so NO number_input/dataframe/slider/charts. Use only text_input, markdown, st.error/warning/info/success.
# Step 2: Quality gate (ROE/ROCE, Debt/Equity, cash flow vs profit, last 4 years; missing = "ડેટા નથી").
# Step 3: Valuation (PE vs own median) + final verdict: Invest candidate / Quality but expensive / Trade-only or Avoid.
# Step 4: manual checklist (promoter, ASM/GSM, SEBI news) + journal saved to journal.csv.
# Step 5: source links per number, conflict flag.
# Run:  pip install streamlit yfinance pandas   then   streamlit run redflag_app.py
import datetime as dt
import pandas as pd
import streamlit as st
import yfinance as yf

ICON = {"ok": "✅", "warn": "⚠️", "bad": "❌", "pend": "⏳"}


def pick(df, names):
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def getq(t):
    cols = ["q", "rev", "pat", "opm"]
    try:
        s = t.quarterly_income_stmt
        if s is None or s.empty:
            return pd.DataFrame(columns=cols)
        rev = pick(s, ["Total Revenue", "Operating Revenue"])
        pat = pick(s, ["Net Income", "Net Income Common Stockholders"])
        op = pick(s, ["Operating Income", "EBIT"])
        rows = []
        for c in sorted(s.columns)[-4:]:
            r = rev[c] / 1e7 if rev is not None else None
            p = pat[c] / 1e7 if pat is not None else None
            o = op[c] / 1e7 if op is not None else None
            opm = o / r * 100 if (o is not None and r) else None
            rows.append({"q": c.strftime("%b-%Y"), "rev": r, "pat": p, "opm": opm})
        df = pd.DataFrame(rows, columns=cols)
        df[["rev", "pat", "opm"]] = df[["rev", "pat", "opm"]].apply(pd.to_numeric, errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(columns=cols)


def nextres(t):
    try:
        c = t.calendar
        e = c.get("Earnings Date") if isinstance(c, dict) else None
        if e:
            d = e[0] if isinstance(e, (list, tuple)) else e
            return pd.to_datetime(d).date()
    except Exception:
        pass
    return None


@st.cache_data(ttl=1800, show_spinner="Yahoo માંથી ડેટા લાવું છું...")
def fetch(sym):
    for suf in (".NS", ".BO"):
        try:
            t = yf.Ticker(sym + suf)
            h = t.history(period="5d")
            if len(h) == 0:
                continue
            return {"tick": sym + suf, "price": float(h["Close"].iloc[-1]),
                    "asof": h.index[-1].date(), "q": getq(t), "nextres": nextres(t)}
        except Exception:
            continue
    return None


def table(df):
    if df.empty:
        return "ક્વાર્ટરના આંકડા Yahoo પર મળ્યા નથી."
    g = lambda v: "ડેટા નથી" if pd.isna(v) else f"{v:,.1f}"
    rows = ["| ક્વાર્ટર | Revenue | Profit | OPM % |", "|---|---|---|---|"]
    for r in df.itertuples():
        rows.append(f"| {r.q} | {g(r.rev)} | {g(r.pat)} | {g(r.opm)} |")
    return "\n".join(rows)


def flags(d):
    f = []
    today = dt.date.today()
    if d["nextres"] is None:
        f.append(("warn", "પરિણામની તારીખ અજાણી"))
    else:
        n = (d["nextres"] - today).days
        if n < 0:
            f.append(("warn", "પરિણામની તારીખ જૂની છે"))
        elif n <= 14:
            f.append(("bad", f"પરિણામ {n} દિવસમાં"))
        elif n <= 30:
            f.append(("warn", f"પરિણામ {n} દિવસમાં"))
        else:
            f.append(("ok", f"પરિણામ {n} દિવસ દૂર (Yahoo અંદાજ)"))
    q = d["q"].dropna(subset=["rev", "pat"])
    if len(q) < 2:
        f.append(("pend", "ક્વાર્ટરના revenue/profit Yahoo પર મળ્યા નથી"))
    else:
        a, b = q.iloc[0], q.iloc[-1]
        if b.rev > a.rev and b.pat < a.pat:
            f.append(("bad", "Revenue વધ્યો પણ profit ઘટ્યો"))
        else:
            f.append(("ok", "Revenue અને profit વચ્ચે વિરોધાભાસ નથી"))
        m = q.dropna(subset=["opm"])
        if len(m) >= 2:
            x = m.opm.iloc[-1] - m.opm.iloc[0]
            if x <= -3:
                f.append(("bad", f"OPM {-x:.1f} પોઇન્ટ ઘટ્યો"))
            elif x < 0:
                f.append(("warn", "OPM થોડો ઘટ્યો"))
            else:
                f.append(("ok", "OPM ટકેલો કે વધ્યો"))
        else:
            f.append(("pend", "OPM મળ્યો નથી"))
    age = (today - d["asof"]).days
    f.append(("warn", f"ભાવનો ડેટા {age} દિવસ જૂનો") if age > 7 else ("ok", "ભાવનો ડેટા તાજો"))
    return f


st.set_page_config(page_title="Stock Red-Flag Dashboard", layout="wide")
st.title("Stock Red-Flag Dashboard")
st.caption("આ સિગ્નલ નથી, ફક્ત red-flag તપાસ છે. 'કોઈ red flag નથી' એટલે સુરક્ષિત એવું નથી.")
sym = st.text_input("શેરનું નામ લખો (NSE symbol, જેમ કે ZYDUSLIFE)").strip().upper()
th = 2
st.caption("છોડવાનો નિયમ: ❌ ની સંખ્યા 2 કે વધુ હોય તો 'છોડી દો'.")

if sym:
    d = fetch(sym)
    if not d:
        st.error("Yahoo પર આ નામ મળ્યું નથી. NSE symbol ફરી તપાસો.")
        st.stop()
    f = flags(d)
    c = {k: sum(x[0] == k for x in f) for k in ("bad", "warn", "pend")}
    if c["bad"] >= th:
        st.error(f"છોડી દો: {c['bad']} red flags")
    elif c["pend"]:
        st.info(f"તપાસ બાકી: {c['pend']} વસ્તુ")
    elif c["bad"] or c["warn"]:
        st.warning(f"સાવચેતી: {c['bad']} ❌, {c['warn']} ⚠️")
    else:
        st.success("કોઈ red flag મળ્યો નથી (સુરક્ષિત હોવાની ખાતરી નથી)")
    st.caption("આ ફક્ત ઓટો-તપાસ છે. Promoter pledge, ASM/GSM, SEBI/ઓડિટર સમાચાર હજી હાથે તપાસવા (Step 4 માં ઉમેરાશે).")
    st.subheader(f"{d['tick']}  ₹{d['price']:.2f}  (ભાવની તારીખ: {d['asof']})")
    for k, t in f:
        st.write(f"{ICON[k]} {t}")
    st.write("છેલ્લા 4 ક્વાર્ટર (₹ કરોડ, જૂના પહેલા)")
    st.markdown(table(d["q"]))
    st.caption("Yahoo ની પરિણામ-તારીખ અંદાજ છે, અને નાના શેરમાં ક્વાર્ટરના આંકડા અધૂરા હોઈ શકે.")
