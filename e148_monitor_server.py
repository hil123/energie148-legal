#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENERGIE148 — Monitoring serveur (Hetzner / Hermes 24-7).
Lit le token Meta depuis /root/.hermes/e148_token.txt (ou $META_ACCESS_TOKEN).
Usage:
  python3 e148_monitor_server.py           -> rapport perf + nb leads (stdout)
  python3 e148_monitor_server.py --leads    -> exporte les leads en CSV (~/e148_leads.csv)
"""
import json, urllib.request, urllib.parse, urllib.error, os, sys, csv, datetime

# ---- Token : env d'abord, sinon fichier ----
TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
if not TOKEN:
    for p in ("/root/.hermes/e148_token.txt", os.path.expanduser("~/e148_token.txt"),
              os.path.expanduser("~/e148_usertoken.txt")):
        if os.path.exists(p):
            TOKEN = open(p, encoding="utf-8").read().strip(); break

ACT   = "act_1361164016080243"
PAGE  = "1194378153753585"
CAMP  = "120247508593550375"
ADSET = "120247518940880375"
GV    = "https://graph.facebook.com/v23.0"
HOME  = os.path.expanduser("~")

def api(path, params=None):
    p = dict(params or {}); p["access_token"] = TOKEN
    url = f"{GV}/{path}?" + urllib.parse.urlencode(p)
    try:
        r = urllib.request.urlopen(url, timeout=30)
        return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: err = json.loads(e.read().decode()).get("error", {})
        except Exception: err = {"message": "unknown"}
        return None, err

def page_token():
    d, err = api(PAGE, {"fields": "access_token"})
    return (d.get("access_token") if d else None), err

LEAD_ACTIONS = ("lead", "leadgen_grouped", "onsite_conversion.lead_grouped")

def report():
    if not TOKEN:
        return "❌ Aucun token Meta trouvé (/root/.hermes/e148_token.txt)."
    out = [f"📊 ENERGIE148 — Rapport campagne ({datetime.datetime.now():%d/%m %H:%M})"]
    me, err = api("me", {"fields": "name"})
    if err:
        out.append(f"⚠️ API Meta indisponible : {err.get('message')}")
        out.append("(Throttle temporaire — réessai au prochain créneau, rien à faire.)")
        return "\n".join(out)

    # Aujourd'hui
    ins, err = api(f"{CAMP}/insights",
        {"fields": "spend,impressions,clicks,ctr,actions", "date_preset": "today"})
    leads_today = spend_today = 0
    if ins and ins.get("data"):
        d = ins["data"][0]; spend_today = float(d.get("spend", 0))
        for a in d.get("actions", []):
            if a["action_type"] in LEAD_ACTIONS: leads_today = int(float(a["value"]))
        cpl = (spend_today / leads_today) if leads_today else 0
        out.append("\n— Aujourd'hui —")
        out.append(f"💸 {spend_today:.2f}€  |  👁 {d.get('impressions','0')} vues  |  🖱 CTR {d.get('ctr','0')}%")
        out.append(f"🎯 {leads_today} leads" + (f"  |  CPL {cpl:.2f}€" if leads_today else ""))

    # Total
    inst, _ = api(f"{CAMP}/insights", {"fields": "spend,actions", "date_preset": "maximum"})
    if inst and inst.get("data"):
        d = inst["data"][0]; st = float(d.get("spend", 0)); lt = 0
        for a in d.get("actions", []):
            if a["action_type"] in LEAD_ACTIONS: lt = int(float(a["value"]))
        out.append("\n— Total campagne —")
        out.append(f"💸 {st:.2f}€ dépensés  |  🎯 {lt} leads" + (f"  |  CPL {st/lt:.2f}€" if lt else ""))

    # Par pub
    ads, _ = api(f"{ADSET}/insights",
        {"fields": "ad_name,spend,ctr,actions", "level": "ad", "date_preset": "maximum"})
    if ads and ads.get("data"):
        out.append("\n— Par publicité —")
        rows = []
        for d in ads["data"]:
            l = 0
            for a in d.get("actions", []):
                if a["action_type"] in LEAD_ACTIONS: l = int(float(a["value"]))
            rows.append((d.get("ad_name", "?"), float(d.get("spend", 0)), l, d.get("ctr", "0")))
        for name, sp, l, ctr in sorted(rows, key=lambda x: -x[2]):
            out.append(f"  • {name}: {l} leads · {sp:.0f}€ · CTR {ctr}%")
    return "\n".join(out)

def export_leads():
    PT, err = page_token()
    if err:
        print("page token err:", err.get("message")); return
    forms, _ = api(f"{PAGE}/leadgen_forms", {"fields": "id,name"})
    rows = []
    for f in (forms.get("data", []) if forms else []):
        try:
            r = urllib.request.urlopen(f"{GV}/{f['id']}/leads?access_token={PT}&limit=200", timeout=30)
            d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            print(f"form {f['id']}: {e.read().decode()[:120]}"); continue
        for lead in d.get("data", []):
            row = {"formulaire": f["name"], "date": lead.get("created_time", "")}
            for fd in lead.get("field_data", []):
                row[fd["name"]] = ", ".join(fd.get("values", []))
            rows.append(row)
    if not rows:
        print("Aucun lead pour l'instant."); return
    keys = sorted({k for r in rows for k in r})
    out = os.path.join(HOME, "e148_leads.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"✅ {len(rows)} leads exportés -> {out}")

if __name__ == "__main__":
    if "--leads" in sys.argv: export_leads()
    else: print(report())
