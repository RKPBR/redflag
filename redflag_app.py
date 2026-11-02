# BUILD LOG (resume from here, do not restart)
# STREAMLIT DASHBOARD (generated from redflag_colab.py, logic identical). Run: python -m streamlit run redflag_app.py, or deploy on Streamlit Community Cloud with requirements.txt
# Step 1 DONE: type share name -> Yahoo (NSE .NS then .BO) -> price, last 4 quarters, auto red flags.
# Step 1b DONE: his loca.lt tunnel blocks lazy-loaded widgets, so NO number_input/dataframe/slider/charts. Use only text_input, markdown, st.error/warning/info/success.
# Step 2 DONE (tested with fake data only): Quality gate = ROCE (else ROE) 15%+ in 3 of 4 yrs, Debt/Equity<1 (not banks/NBFC), cash flow 80%+ of profit, profit growing; flag when Yahoo skips a quarter.
# Step 2b DONE (fake data only): loss-quarter flags (Delta Corp case), Utilities exempt from ROCE/D-E + interest coverage check (NTPC case).
# Step 3 DONE (fake data only): Valuation (annual profit/shares, year-end PE vs own median, fair if <=1.2x) + final decision on top.
# Step 4 DONE (fake data only): AUTO checks = Google News headline scan, NSE ASM/GSM lists (unverified endpoints, sanity-checked), Yahoo insider %; pledge cannot be automated.
# Step 4 (old plan): manual checklist (promoter, ASM/GSM, SEBI news) + journal saved to journal.csv.
# Step 5 DONE (fake data only): journal.csv auto-saved each check + previous-checks line + summary + download buttons + source links + Yahoo PE cross-check.
# Run:  pip install streamlit yfinance pandas   then   streamlit run redflag_app.py
import streamlit as st
import time
import datetime as dt
import os, csv, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
import requests
import pandas as pd
import yfinance as yf

ICON = {"info": "ℹ️", "ok": "✅", "warn": "⚠️", "bad": "❌", "pend": "⏳"}


def pick(df, names):
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def getq(t):
    cols = ["q", "rev", "pat", "opm", "d"]
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
            rows.append({"q": c.strftime("%b-%Y"), "rev": r, "pat": p, "opm": opm, "d": c.date()})
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


def _fetch(sym):
    rl = False
    for suf in (".NS", ".BO"):
        for _ in range(3):
            try:
                t = yf.Ticker(sym + suf)
                try:
                    h = t.history(period="5d", raise_errors=True)
                except TypeError:
                    h = t.history(period="5d")
                if len(h) == 0:
                    break
                return {"tick": sym + suf, "price": float(h["Close"].iloc[-1]),
                        "asof": h.index[-1].date(), "q": getq(t), "nextres": nextres(t),
                        "ann": getann(t), "sector": getsector(t), "hist": gethist(t),
                        "name": getname(t), "hold": getholders(t), "ype": getype(t)}
            except Exception as e:
                if "rate" in str(e).lower() or "too many" in str(e).lower():
                    rl = True
                    time.sleep(2)
                    continue
                break
    return {"rate_limited": True} if rl else None


def gethist(t):
    try:
        h = t.history(period="10y")["Close"]
        if getattr(h.index, "tz", None) is not None:
            h.index = h.index.tz_localize(None)
        return h
    except Exception:
        return None


def valuation(d):
    d["pe_now"] = d["pe_med"] = None
    a, h = d["ann"], d.get("hist")
    if a.empty or h is None or len(h) == 0 or not {"ni", "sh"} <= set(a.columns) or "dates" not in a.attrs:
        return "pend", ["⏳ ભાવ તપાસ માટે ડેટા નથી"]
    pes, eps_last = [], None
    for dte, (lab, r) in zip(a.attrs["dates"], a.iterrows()):
        eps = r["ni"] / r["sh"] if pd.notna(r["ni"]) and pd.notna(r["sh"]) and r["sh"] > 0 else None
        if eps is not None:
            eps_last = eps
        p = h[:dte]
        if eps and eps > 0 and len(p):
            pes.append((lab, float(p.iloc[-1] / eps)))
    if not eps_last or eps_last <= 0:
        return "pend", ["⏳ ભાવ તપાસ લાગુ નથી (છેલ્લા વર્ષનો નફો નકારાત્મક કે ડેટા નથી)"]
    now = d["price"] / eps_last
    lines = [f"કમાણી સામે ભાવ (PE): હાલ {now:.1f} ગણો"]
    d["pe_now"] = now
    y = d.get("ype")
    if y:
        far = abs(y / now - 1) > 0.25
        lines.append(("⚠️" if far else "ℹ️") + f" બીજી ગણતરી મુજબ PE: {y:.1f}" + (" — મારી ગણતરીથી બહુ જુદો, વાર્ષિક નફો જૂનો હોઈ શકે" if far else ""))
    if len(pes) < 3:
        return "pend", lines + ["⏳ આ શેરનો પોતાનો ઇતિહાસ ટૂંકો છે (3 વર્ષથી ઓછો), સરખામણી શક્ય નથી"]
    med = float(pd.Series([x[1] for x in pes]).median())
    lines.append("આ શેરના પાછલા વર્ષોનો PE: " + ", ".join(f"{x[1]:.0f}" for x in pes) + f" → મધ્યમ {med:.1f}")
    d["pe_med"] = med
    ratio = now / med
    ok = ratio <= 1.2
    lines.append(("✅" if ok else "❌") + f" હાલનો ભાવ સામાન્ય સ્તરના {ratio:.2f} ગણો — " + ("વાજબી" if ok else "મોંઘો (1.2 ગણાથી વધુ)"))
    return ("ok" if ok else "bad"), lines


def decide(rf_bad, qc, vs, hard=0):
    if rf_bad >= 2 or hard:
        return "⛔ હમણાં નહીં", "ચેતવણીઓ સ્પષ્ટ થાય પછી ફરી જુઓ (કંપની સારી હોય તોયે)"
    if qc["bad"] >= 2:
        return "🔶 લાંબા ગાળા માટે નહીં", "ફક્ત trade (stop-loss સાથે) કે છોડો"
    if qc["bad"] == 0 and qc["pend"] == 0:
        if vs == "ok":
            return "✅ લાંબા ગાળા માટે વિચારી શકાય", "3 હપ્તામાં ખરીદી, નિયમો પહેલાં લખી રાખો"
        if vs == "bad":
            return "🟡 કંપની સારી, ભાવ મોંઘો", "યાદીમાં રાખો, ભાવ ઘટે કે નફો વધે ત્યારે ફરી જુઓ"
        return "🟡 કંપની સારી, ભાવ તપાસ અધૂરી", "ભાવ હાથે તપાસો"
    return "🟡 મિશ્ર ચિત્ર", "હાથે વધુ તપાસ કરો"


def getname(t):
    try:
        n = t.info.get("longName") or t.info.get("shortName") or ""
        return re.sub(r"\b(limited|ltd\.?)\b", "", n, flags=re.I).strip()
    except Exception:
        return ""


def getholders(t):
    try:
        return float(t.major_holders.loc["insidersPercentHeld"].iloc[0]) * 100
    except Exception:
        return None


UA = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "accept": "application/json,text/plain,*/*", "accept-language": "en-US,en;q=0.9"}
RISK = re.compile(r"\b(SEBI|fraud|probe|raid|penalt\w*|auditor|resign\w*|default\w*|insolvenc\w*|NCLT|arrest\w*|CBI|scam|show[- ]cause|forensic|whistleblow\w*|investigation|GST demand|tax demand|pledg\w*)\b", re.I)


def news(name):
    try:
        q = urllib.parse.quote(f'"{name}" (SEBI OR fraud OR penalty OR probe OR auditor OR default OR raid OR insolvency) when:90d')
        u = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
        root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=15).read())
        return [(i.findtext("title") or "", i.findtext("pubDate") or "", i.findtext("link") or "") for i in root.iter("item")]
    except Exception:
        return None


def nse_lists(sym):
    res = {"ASM": None, "GSM": None}
    try:
        H = dict(UA, referer="https://www.nseindia.com/")
        ss = requests.Session()
        ss.get("https://www.nseindia.com", headers=H, timeout=12)
        for k in res:
            txt = ss.get(f"https://www.nseindia.com/api/report{k}", headers=H, timeout=12).text
            syms = {x.upper() for x in re.findall(r'"symbol"\s*:\s*"([^"]+)"', txt, re.I)}
            if len(syms) >= 3:
                res[k] = sym in syms
    except Exception:
        pass
    return res


def extras(d):
    sym = d["tick"].split(".")[0].upper()
    nm = d.get("name") or sym
    out, bad = [], 0
    h = d.get("hold")
    out.append(f"ℹ️ માલિકો (promoter) નો હિસ્સો આશરે {h:.1f}% (વધ-ઘટનો ટ્રેન્ડ નથી)" if h is not None else "⏳ માલિકોનો હિસ્સો મળ્યો નથી")
    out.append("ℹ️ માલિકોએ શેર ગીરો મૂક્યા છે કે નહીં (pledge) ઓટોથી જાણી શકાતું નથી, નીચેની Screener લિંકમાં જુઓ.")
    r = nse_lists(sym)
    for k in ("ASM", "GSM"):
        if r[k] is True:
            out.append(f"❌ {k} (NSE ની ખાસ નજર હેઠળની) યાદીમાં છે")
            bad += 1
        elif r[k] is False:
            out.append(f"✅ {k} યાદીમાં નથી")
        else:
            out.append(f"⏳ {k} યાદી ઓટો ન મળી, હાથે જુઓ")
    items = news(nm)
    if items is None:
        out.append("⏳ સમાચાર ઓટો ન મળ્યા (ઇન્ટરનેટ/Google)")
    else:
        key = nm.split()[0].lower()
        hits = [x for x in items if RISK.search(x[0]) and key in x[0].lower()]
        if not hits:
            out.append("✅ છેલ્લા 90 દિવસના સમાચાર-મથાળાંમાં જોખમી શબ્દો નથી (અધૂરી તપાસ)")
        else:
            out.append(f"⚠️ {len(hits)} સમાચાર-મથાળાંમાં જોખમી શબ્દો (આપમેળે શોધ્યા, અચોક્કસ, વાંચી જુઓ):")
            out += [f"- [{x[0].replace('[', '(').replace(']', ')')}]({x[2]}) ({x[1][:16]})" for x in hits[:5]]
    return out, bad


def getsector(t):
    try:
        return t.info.get("sector") or ""
    except Exception:
        return ""


def getann(t):
    try:
        i, b, c = t.income_stmt, t.balance_sheet, t.cashflow
        spec = {"ni": (i, ["Net Income", "Net Income Common Stockholders"]), "ebit": (i, ["EBIT", "Operating Income"]),
                "eq": (b, ["Stockholders Equity", "Common Stock Equity"]), "debt": (b, ["Total Debt"]),
                "ta": (b, ["Total Assets"]), "cl": (b, ["Current Liabilities"]),
                "sh": (b, ["Ordinary Shares Number", "Share Issued"]),
                "cfo": (c, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
                "intr": (i, ["Interest Expense", "Interest Expense Non Operating"])}
        out = {}
        for k, (df, names) in spec.items():
            x = pick(df, names) if df is not None and not df.empty else None
            if x is not None:
                out[k] = x / 1e7
        a = pd.DataFrame(out).sort_index().tail(4)
        dates = list(a.index)
        a.index = [x.strftime("%b-%y") for x in a.index]
        a.attrs["dates"] = dates
        return a
    except Exception:
        return pd.DataFrame()


def _quality(d):
    a, f = d["ann"], []
    if a.empty or len(a) < 2:
        return [("pend", "વાર્ષિક ડેટા મળ્યો નથી")]
    cs = set(a.columns)
    fin = "Financial" in (d["sector"] or "")
    f.append(("warn", f"ફક્ત {len(a)} વર્ષનો ડેટા") if len(a) < 4 else ("ok", f"{len(a)} વર્ષનો ડેટા"))
    r = None
    if not fin and {"ebit", "ta", "cl"} <= cs:
        r, nm = a.ebit / (a.ta - a.cl) * 100, "ROCE"
    elif {"ni", "eq"} <= cs:
        r, nm = a.ni / a["eq"] * 100, "ROE"
    r = r.dropna() if r is not None else None
    if r is None or len(r) == 0:
        f.append(("pend", "મૂડી પર કમાણી: ડેટા નથી"))
    else:
        k = int((r >= 15).sum())
        f.append(("ok" if k >= min(3, len(r)) else "bad", f"મૂડી પર કમાણી ({nm}): " + ", ".join(f"{v:.0f}%" for v in r) + f" — {k}/{len(r)} વર્ષ 15% થી વધુ (સારું)"))
    if fin:
        f.append(("pend", "દેવું: બેંક/NBFC માટે આ ધોરણ લાગુ નથી, NPA (ખરાબ લોન) હાથે તપાસો"))
    elif {"debt", "eq"} <= cs and pd.notna(a["eq"].iloc[-1]) and a["eq"].iloc[-1] > 0 and pd.notna(a.debt.iloc[-1]):
        x = a.debt.iloc[-1] / a["eq"].iloc[-1]
        f.append(("ok" if x < 1 else "bad", f"દેવું (Debt/Equity): પોતાની મૂડી સામે {x:.2f} ગણું — 1 થી ઓછું સારું"))
    else:
        f.append(("pend", "દેવું: ડેટા નથી"))
    s = a[["cfo", "ni"]].dropna() if {"cfo", "ni"} <= cs else None
    if s is None or len(s) == 0:
        f.append(("pend", "રોકડ પ્રવાહ: ડેટા નથી"))
    elif s.ni.sum() <= 0:
        f.append(("bad", "નફાની વૃદ્ધિ: કુલ નફો નકારાત્મક કે શૂન્ય"))
    else:
        x = s.cfo.sum() / s.ni.sum() * 100
        f.append(("ok" if x >= 80 else "bad", f"રોકડ પ્રવાહ: નફો રોકડમાં કેટલો આવ્યો {x:.0f}% — 80% થી વધુ સારું"))
    v = a.ni.dropna() if "ni" in cs else []
    if len(v) >= 2:
        f.append(("ok" if v.iloc[-1] > v.iloc[0] else "bad", f"નફાની વૃદ્ધિ: {v.iloc[0]:,.0f} થી {v.iloc[-1]:,.0f} ₹ કરોડ"))
    return f


def quality(d):
    f = _quality(d)
    a = d["ann"]
    if d["sector"] == "Utilities":
        f = [("pend", t + " (regulated ક્ષેત્રમાં આ ધોરણ લાગુ નથી)") if (k == "bad" and t.startswith(("મૂડી પર કમાણી", "દેવું"))) else (k, t) for k, t in f]
    if not a.empty and "Financial" not in (d["sector"] or "") and {"ebit", "intr"} <= set(a.columns):
        e, i = a.ebit.iloc[-1], abs(a.intr.iloc[-1])
        if pd.notna(e) and pd.notna(i) and i > 0:
            x = e / i
            f.append(("ok" if x >= 3 else "bad", f"વ્યાજ ભરવાની તાકાત: {x:.1f} ગણી — 3 થી વધુ સારી"))
    return f


def table(df):
    if df.empty:
        return "ક્વાર્ટરના આંકડા મળ્યા નથી."
    g = lambda v: "ડેટા નથી" if pd.isna(v) else f"{v:,.1f}"
    rows = ["| ક્વાર્ટર | વેચાણ | નફો | નફા-ગાળો % |", "|---|---|---|---|"]
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
            f.append(("ok", f"પરિણામ {n} દિવસ દૂર (અંદાજ)"))
    q = d["q"].dropna(subset=["rev", "pat"])
    if len(q) < 2:
        f.append(("pend", "ક્વાર્ટરના વેચાણ/નફાનો ડેટા મળ્યો નથી"))
    else:
        a, b = q.iloc[0], q.iloc[-1]
        if b.rev > a.rev and b.pat < a.pat:
            f.append(("bad", "વેચાણ વધ્યું પણ નફો ઘટ્યો"))
        else:
            f.append(("ok", "વેચાણ અને નફો સાથે ચાલે છે (વિરોધાભાસ નથી)"))
        if int((q.pat.tail(2) < 0).sum()) == 2:
            f.append(("bad", "છેલ્લા 2 ક્વાર્ટરમાં ચોખ્ખી ખોટ"))
        elif b.pat < 0:
            f.append(("bad", "છેલ્લા ક્વાર્ટરમાં ચોખ્ખી ખોટ"))
        if b.pat < 0 and pd.notna(b.opm) and b.opm > 0:
            f.append(("warn", "ધંધામાં નફો છે છતાં ચોખ્ખી ખોટ: એક-વારનો ખર્ચ કે જોગવાઈ હોઈ શકે, સમાચાર વાંચો"))
        m = q.dropna(subset=["opm"])
        if len(m) >= 2:
            x = m.opm.iloc[-1] - m.opm.iloc[0]
            if x <= -3:
                f.append(("bad", f"ધંધાનો નફા-ગાળો (margin) {-x:.1f} પોઇન્ટ ઘટ્યો"))
            elif x < 0:
                f.append(("warn", "નફા-ગાળો (margin) થોડો ઘટ્યો"))
            else:
                f.append(("ok", "નફા-ગાળો (margin) ટકેલો કે વધ્યો"))
        else:
            f.append(("pend", "નફા-ગાળો મળ્યો નથી"))
    ds = d["q"].get("d")
    if ds is not None:
        ds = list(ds.dropna())
        if len(ds) >= 2 and max((y - x).days for x, y in zip(ds, ds[1:])) > 120:
            f.append(("warn", "એક ક્વાર્ટરનો ડેટા ખૂટે છે, સરખામણી અધૂરી"))
    age = (today - d["asof"]).days
    f.append(("warn", f"ભાવનો ડેટા {age} દિવસ જૂનો") if age > 7 else ("ok", "ભાવનો ડેટા તાજો"))
    return f


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_ok(sym):
    v = _fetch(sym)
    if v is None or v.get("rate_limited"):
        raise LookupError(v)
    return v


def fetch(sym):
    try:
        return _fetch_ok(sym)
    except LookupError as e:
        return e.args[0]


def getype(t):
    try:
        v = t.info.get("trailingPE")
        return float(v) if v else None
    except Exception:
        return None


JF = "journal.csv"
JC = ["time", "symbol", "tick", "price", "price_date", "decision", "red_flags", "quality", "valuation", "pe_now", "pe_median"]


def jprev(sym, price):
    try:
        rows = [r for r in csv.DictReader(open(JF, encoding="utf-8")) if r["symbol"] == sym][-3:]
        return [f"- {r['time']}: {r['decision']} (ભાવ ₹{r['price']}) → હવે {(price / float(r['price']) - 1) * 100:+.1f}%" for r in rows]
    except Exception:
        return []


def jwrite(d, title, c, qv, vs):
    try:
        new = not os.path.exists(JF)
        with open(JF, "a", newline="", encoding="utf-8") as fh:
            w_ = csv.writer(fh)
            if new:
                w_.writerow(JC)
            pn, pm = d.get("pe_now"), d.get("pe_med")
            w_.writerow([dt.datetime.now().strftime("%Y-%m-%d %H:%M"), d["tick"].split(".")[0], d["tick"], round(d["price"], 2),
                         d["asof"], title, c["bad"], qv, vs, round(pn, 1) if pn else "", round(pm, 1) if pm else ""])
    except Exception:
        pass


def jsummary():
    try:
        rows = list(csv.DictReader(open(JF, encoding="utf-8")))
    except Exception:
        rows = []
    if not rows:
        return "Journal હજી ખાલી છે. પહેલા એક-બે શેર તપાસો."
    cur = {}
    for t in {r["tick"] for r in rows}:
        try:
            cur[t] = float(yf.Ticker(t).history(period="5d")["Close"].iloc[-1])
        except Exception:
            pass
    g = {}
    for r in rows:
        if r["tick"] in cur:
            g.setdefault(r["decision"], []).append((cur[r["tick"]] / float(r["price"]) - 1) * 100)
    L = ["### Journal સારાંશ (તપાસ સમયના ભાવથી હાલ સુધી)", "| નિર્ણય | તપાસ | સરેરાશ ફેરફાર % |", "|---|---|---|"]
    L += [f"| {k} | {len(v)} | {sum(v) / len(v):+.1f} |" for k, v in g.items()]
    L.append("*થોડા અઠવાડિયામાં આ આંકડા અર્થહીન છે (નાનો નમૂનો). મહિનાઓ પછી, વધુ તપાસ સાથે જ જુઓ.*")
    return L[0] + "\n\n" + "\n".join(L[1:-1]) + "\n\n" + L[-1]


def analyze(sym, th=2):
    d = fetch(sym)
    if not d:
        return {"msg": "❌ આ નામ મળ્યું નથી. NSE નું નામ ફરી તપાસો (જેમ કે TCS)."}
    if d.get("rate_limited"):
        return {"msg": "⚠️ ડેટા આપનાર સાઇટે હમણાં વિનંતીઓ રોકી છે. 5-10 મિનિટ પછી ફરી પ્રયત્ન કરો."}
    f = flags(d)
    ex, exb = extras(d)
    c = {k: sum(x[0] == k for x in f) for k in ("bad", "warn", "pend")}
    c["bad"] += exb
    qf = quality(d)
    qc = {k: sum(x[0] == k for x in qf) for k in ("bad", "pend")}
    vs, vl = valuation(d)
    title, why = decide(c["bad"], qc, vs, exb)
    lab = lambda t: t.split(":")[0].split(" (")[0]
    qbad = [lab(t) for k, t in qf if k == "bad" and "વર્ષનો ડેટા" not in t]
    qok = [lab(t) for k, t in qf if k == "ok" and "વર્ષનો ડેટા" not in t]
    if qc["bad"] >= 2:
        co, qv = "❌ નબળી. નબળા મુદ્દા: " + ", ".join(qbad), "❌ નબળી"
    elif qc["bad"] == 0 and qc["pend"] == 0:
        co, qv = "✅ સારી. " + ", ".join(qok) + ": બધું સારું", "✅ સારી"
    else:
        co, qv = "⚠️ મિશ્ર. " + (("નબળા મુદ્દા: " + ", ".join(qbad)) if qbad else "કેટલીક તપાસ અધૂરી"), "⚠️ મિશ્ર"
    pn, pm = d.get("pe_now"), d.get("pe_med")
    r = f" (હાલનો ભાવ સામાન્ય સ્તરના {pn / pm:.2f} ગણો)" if pn and pm else ""
    pr = {"ok": "✅ વાજબી" + r, "bad": "❌ મોંઘો" + r, "pend": "⏳ ખબર નથી, ડેટા અધૂરો"}[vs]
    ign = ("પરિણામની તારીખ", "ભાવનો ડેટા")
    wl = [t for k, t in f if k in ("bad", "warn") and not t.startswith(ign)]
    wl += [l[2:].strip() for l in ex if l.startswith("❌")]
    if any(l.startswith("⚠️") and "મથાળાં" in l for l in ex):
        wl.append("સમાચારમાં જોખમી શબ્દો મળ્યા, નીચે વાંચી જુઓ")
    ws = "✅ કોઈ મોટી ચેતવણી નથી" if not wl else ("❌ " if c["bad"] else "⚠️ ") + " • ".join(wl)
    sy = d["tick"].split(".")[0]
    pv = jprev(sy, d["price"])
    q_ = urllib.parse.quote(sy)
    links = f"[Yahoo](https://finance.yahoo.com/quote/{d['tick']}) · [Screener](https://www.screener.in/company/{q_}/) · [NSE](https://www.nseindia.com/get-quotes/equity?symbol={q_})"
    jwrite(d, title, c, qv, vs)
    return {"tick": d["tick"], "price": d["price"], "asof": d["asof"], "title": title, "why": why, "co": co, "pr": pr, "ws": ws,
            "prev": pv, "flags": [f"{ICON[k]} {t}" for k, t in f], "table": table(d["q"]),
            "quality": [f"{ICON[k]} {t}" for k, t in qf], "val": vl, "extras": ex, "links": links}


st.set_page_config(page_title="શેર તપાસ", layout="centered")
st.title("શેર તપાસ")
st.caption("આ સલાહ નથી, તપાસનો સારાંશ છે. અંતિમ નિર્ણય તમારો.")
with st.form("f"):
    sym = st.text_input("શેરનું નામ (NSE), જેમ કે TCS").strip().upper()
    go = st.form_submit_button("તપાસો")
if go and sym:
    with st.spinner("તપાસ ચાલે છે..."):
        try:
            st.session_state["a"] = analyze(sym)
        except Exception as e:
            st.session_state["a"] = {"msg": f"❌ કંઈક ભૂલ આવી: {e}"}
a = st.session_state.get("a")
if a and a.get("msg"):
    st.error(a["msg"])
elif a:
    st.subheader(f"{a['tick']}   ₹{a['price']:.2f}")
    st.caption(f"ભાવની તારીખ: {a['asof']}")
    {"✅": st.success, "⛔": st.error}.get(a["title"][0], st.warning)(f"**{a['title']}**\n\n{a['why']}")
    st.markdown(f"**કંપની કેવી છે?** {a['co']}\n\n**ભાવ કેવો છે?** {a['pr']}\n\n**હમણાં ચેતવણી?** {a['ws']}")
    if a["prev"]:
        st.markdown("**પહેલાંની તપાસ:**\n" + "\n".join(a["prev"]))
    with st.expander("ચેતવણીઓની વિગત"):
        st.markdown("\n\n".join(a["flags"]))
    with st.expander("છેલ્લા 4 ક્વાર્ટરનો ધંધો (₹ કરોડ)"):
        st.markdown(a["table"])
    with st.expander("કંપનીની ગુણવત્તા: વિગત"):
        st.markdown("\n\n".join(a["quality"]))
    with st.expander("ભાવ (PE) ની વિગત"):
        st.markdown("\n\n".join(a["val"]))
    with st.expander("સમાચાર, NSE અને માલિકોની તપાસ"):
        st.markdown("\n\n".join(a["extras"]))
    with st.expander("ચકાસવા લિંક અને ડેટા વિશે"):
        st.markdown("**ચકાસવા માટે:** " + a["links"] + "\n\nઆંકડા Yahoo Finance, NSE અને Google News ના છે (કંપનીના આંકડા ફક્ત ~4 વર્ષના). ધોરણો (15%, 1.2 ગણો વગેરે) મારા શરૂઆતના છે, ચકાસેલા નથી.")
with st.expander("શબ્દોનો સરળ અર્થ"):
    st.markdown("""- **PE:** ભાવ ÷ એક વર્ષની કમાણી. 20 એટલે 20 વર્ષની કમાણી જેટલો ભાવ. ઓછો હોય તો સસ્તો.
- **મૂડી પર કમાણી (ROCE/ROE):** ₹100 ની મૂડી સામે વર્ષે કેટલા કમાય. 15 થી વધુ સારું.
- **દેવું (Debt/Equity):** પોતાની મૂડી સામે કેટલું દેવું. 1 થી ઓછું સારું.
- **નફા-ગાળો (margin):** ₹100 ના વેચાણમાંથી કેટલો ધંધાનો નફો.
- **રોકડ પ્રવાહ:** નફો ચોપડે જ છે કે ખરેખર રોકડમાં પણ આવ્યો.
- **ASM/GSM:** NSE ની ખાસ નજર હેઠળના શંકાસ્પદ શેરોની યાદી.
- **Promoter / pledge:** કંપનીના માલિકો / માલિકોએ લોન માટે ગીરો મૂકેલા શેર.""")
st.divider()
c1, c2 = st.columns(2)
if c1.button("જર્નલ સારાંશ"):
    st.markdown(jsummary())
if os.path.exists(JF):
    c2.download_button("જર્નલ ડાઉનલોડ", open(JF, "rb").read(), "journal.csv", "text/csv")
