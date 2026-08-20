# Surf check

Kijkt twee keer per dag naar de forecast op 26 spots in Marokko, Portugal,
Spanje, Frankrijk, Engeland en Ierland. Zit er een blok goede dagen aan te
komen dat te bereiken is, dan valt er één voorstel in de Telegram-groep —
swell, vlucht, auto, materiaal, bed en een totaalprijs.

Draait op GitHub Actions. Geen server, geen abonnement.

---

## Hoe het beslist

**Per uur** wordt gekeken naar hoogte, periode, wind en deiningsrichting.
Elk van die vier is een harde eis. Wat overblijft krijgt een score van 0-100,
waarin periode het zwaarst weegt.

**Per dag** telt alleen het ochtendvenster (06:00-11:00 lokaal), met minstens
drie aaneengesloten goede uren. Aan de kust trekt de thermische zeewind bijna
dagelijks rond elf uur aan; zou je eisen dat de wind de hele dag onder tien
knopen blijft, dan gaat dit ding vrijwel nooit af.

**Per blok** moeten er genoeg goede dagen op rij zijn: twee voor de nabije
regio's, drie voor Marokko, Ierland, Engeland en de Algarve.

**Twee alarmniveaus.** Zit de swell 6-9 dagen weg, dan krijg je een vroege
waarschuwing. Komt hij binnen vijf dagen, dan volgt de bevestiging. Een swell
die al gemeld is komt niet nog eens langs.

### De criteria

| | Waarde |
|---|---|
| Golfhoogte | 5-12 ft brekende golf |
| Periode | minimaal 8s |
| Wind | 0-10kt uit elke richting, of tot 15kt mits offshore |
| Venster | 06:00-11:00 lokaal, minstens 3 uur aaneen |
| Dagen | 2 dichtbij, 3 ver weg |
| Vluchten | alleen direct |
| Bed | maximaal EUR 50 per nacht p.p., gratis annuleren |

---

## Vliegvelden: pools per regio

Elke spot hangt aan een **regio** met meerdere vliegvelden, en heeft per
vliegveld een rijtijd. Hossegor is bijvoorbeeld te doen vanaf Biarritz
(40 min), San Sebastián (75), Bordeaux (105) én Bilbao (145).

Dat is met opzet zo: welke vliegvelden direct bereikbaar zijn verschilt per
seizoen. Bordeaux en Biarritz worden in de zomer wél vanuit Nederland gevlogen
en in oktober niet. Door de hele pool te doorzoeken corrigeert het systeem
zichzelf, zonder dat iemand een lijst hoeft bij te werken.

**Winnaar is niet de goedkoopste vlucht** maar de laagste totale kosten per
behouden surfsessie. Een vlucht die je een ochtend kost verliest van een
duurdere die hem behoudt; een trip die een nacht langer duurt moet die extra
nacht aan auto, bed en materiaal goedmaken. Rijtijd telt licht mee.

---

## Opzetten

**1. Telegram-bot** — via `@BotFather`, `/newbot`. Voeg de bot toe aan een
groep, stuur er een bericht dat met `/` begint, en haal het chat-id op via
`https://api.telegram.org/bot<TOKEN>/getUpdates`.

**2. Apify-account** — gratis, op [apify.com](https://apify.com). Kopieer je
API-token. Zet ook een maandlimiet in je account als extra zekerheid.

**3. Secrets** — Settings → Secrets and variables → Actions:

| Naam | Waarde |
|---|---|
| `TELEGRAM_BOT_TOKEN` | het token van BotFather |
| `TELEGRAM_CHAT_ID` | het negatieve groepsnummer |
| `APIFY_TOKEN` | je Apify API-token |

**4. Testen** — Actions → Surf check → Run workflow, met "Testbericht" aan.
Er valt dan een verzonnen voorstel in de groep zodat je ziet dat alles werkt.

---

## Aanpassen

Alles staat in `config.yaml`, met uitleg bovenaan. De knoppen die je het
vaakst nodig hebt:

- **Minder meldingen:** `min_day_score` omhoog (55 → 65), of `min_period_s`
  naar 10.
- **Meer meldingen:** `min_day_score` omlaag, of `max_wind_kt` omhoog.
- **Verder willen rijden:** `max_drive_min` omhoog.
- **Overstap toestaan:** `direct_only` op `false`.

In `stays.yaml` vul je zelf slaapplekken aan waar je geweest bent. Staat er
iets voor de spot waar de swell is, dan zet het voorstel dat erbij in plaats
van alleen een zoeklink.

---

## Databronnen

**[Open-Meteo](https://open-meteo.com)** voor de forecast — gratis, geen
sleutel. Marine-model voor de deining, weermodel voor de wind, samengevoegd
op tijdstempel. Alle spots in één gebundelde aanroep. Of de wind offshore is
rekent het script zelf uit uit de kustorientatie per spot.

**Apify (Google Flights)** voor de vluchten. De bestemmingen die er voor ons
toe doen worden door Transavia, KLM, easyJet en Ryanair door elkaar gevlogen;
één maatschappij bevragen mist het meeste. Kosten zijn verwaarloosbaar —
ongeveer een cent per duizend resultaten, en er wordt alleen gezocht als er
al een swell door de filters is. In de aanroep zit een harde uitgavenlimiet.

Er is **geen terugval** op een tweede vluchtbron. Valt Apify om, dan zegt het
bericht dat met de foutmelding erbij. Twee half werkende bronnen naast elkaar
is meer onderhoud dan een duidelijke storingsmelding.

**Auto en bed worden niet gescrapet** — daar bestaat geen gratis betrouwbare
bron voor. Je krijgt een richtprijs voor de begroting plus een zoeklink met
datums, coordinaten en prijsplafond er al in.

## Lokaal draaien

```bash
pip install -r requirements.txt
python main.py --dry-run --verbose    # echte forecast, niets versturen
python main.py --demo --dry-run       # verzonnen swell, bericht bekijken
python test_logic.py                  # 65 controles op de beslislogica
```
