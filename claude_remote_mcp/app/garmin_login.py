"""Inlogpagina voor een Garmin-account: /login/<slug>?token=<gateway_token>.

Garmin stuurt bij een nieuwe login soms een beveiligingscode per mail. Op deze pagina start je de login,
vul je die code in, en daarna bewaart de add-on de sessie (garmin_tokens.json in de sessiemap), zodat er
geen nieuwe code nodig is zolang die sessie geldig blijft. Beveiligd met hetzelfde gateway_token als de
MCP-adressen (BearerAuthMiddleware); het formulier post naar hetzelfde adres, dus het token gaat mee.
"""

from html import escape
from urllib.parse import parse_qs

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.garmin_tools import garmin_accounts, masker

STIJL = """
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: #070b18; color: #e8ecf6; }
main { max-width: 420px; margin: 0 auto; padding: 32px 20px; }
h1 { font-size: 24px; margin: 0 0 6px; } p { line-height: 1.5; color: #b8c0d6; }
.kaart { background: #10172b; border: 1px solid #222b45; border-radius: 16px; padding: 18px; margin-top: 18px; }
input { width: 100%; box-sizing: border-box; font-size: 28px; letter-spacing: .3em; text-align: center; padding: 12px;
  border-radius: 12px; border: 1px solid #2d3858; background: #0b1122; color: #fff; }
button { width: 100%; margin-top: 12px; padding: 14px; font-size: 16px; font-weight: 700; border: 0; border-radius: 12px;
  background: #c6f432; color: #07101f; }
button.rustig { background: transparent; color: #e8ecf6; border: 1px solid #2d3858; font-weight: 600; }
.ok { color: #4ade80; font-weight: 700; } .fout { color: #f87171; }
"""


def pagina(titel: str, inhoud: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{escape(titel)}</title><style>{STIJL}</style></head><body><main>{inhoud}</main></body></html>""",
        status_code=status,
        headers={"cache-control": "no-store"},
    )


async def garmin_login(request: Request) -> HTMLResponse:
    account = garmin_accounts.get(request.path_params["slug"])
    if account is None:
        return pagina("Onbekend account", "<h1>Onbekend account</h1><p>Dit Garmin-account is niet ingesteld in de add-on.</p>", 404)

    melding = ""
    if request.method == "POST":
        form = parse_qs((await request.body()).decode())
        actie = (form.get("actie") or [""])[0]
        try:
            if actie == "code":
                await run_in_threadpool(account.code_invullen, (form.get("code") or [""])[0])
            elif actie == "start":
                await run_in_threadpool(account.inloggen)
        except Exception as e:  # noqa: BLE001 - de fout tonen we gewoon op de pagina
            melding = f'<p class="fout">Dat lukte niet: {escape(str(e))}</p>'

    wie = escape(masker(account.email))
    kop = f"<h1>Garmin koppelen</h1><p>Account: {wie}</p>"
    if account.status == "ingelogd":
        blok = f'<p class="ok">✓ Gekoppeld.</p><p>De sessie is bewaard; de app haalt de Garmin-data van {wie} vanaf nu zelf op. Je kunt deze pagina sluiten.</p>'
    elif account.status == "wacht_op_code":
        blok = f"""<p>Garmin heeft een code gemaild naar <b>{wie}</b>. Vul hem hier in (hij is maar even geldig):</p>
<form method="post"><input type="hidden" name="actie" value="code">
<input name="code" inputmode="numeric" autocomplete="one-time-code" required maxlength="10" autofocus>
<button type="submit">Inloggen</button></form>
<form method="post"><input type="hidden" name="actie" value="start"><button class="rustig" type="submit">Nieuwe code sturen</button></form>"""
    else:
        fout = f'<p class="fout">Laatste poging: {escape(account.laatste_fout)}</p>' if account.laatste_fout else ""
        blok = f"""<p>Nog niet ingelogd. Na op de knop te tikken stuurt Garmin misschien een code naar {wie}; die vul je hierna in.</p>{fout}
<form method="post"><input type="hidden" name="actie" value="start"><button type="submit">Inloggen bij Garmin</button></form>"""
    return pagina("Garmin koppelen", f'{kop}{melding}<div class="kaart">{blok}</div>')
