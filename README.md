# Surf check

Kijkt twee keer per dag naar de forecast op 26 spots in Marokko, Portugal,
Spanje, Frankrijk, Engeland en Ierland. Zit er een blok goede dagen aan te
komen dat binnen budget te bereiken is, dan valt er één voorstel in de
Telegram-groep — swell, vlucht, auto, bed, totaalprijs, en een poll.

Draait gratis op GitHub Actions. Geen server, geen abonnement, geen scrapers.

---

## Opzetten (eenmalig, ~10 minuten)

**1. Telegram-bot maken**

Open Telegram, zoek `@BotFather`, stuur `/newbot`. Kies een naam. Je krijgt
een token terug (`8123456789:AAF...`). Bewaar die.

**2. Bot in je groep zetten**

Maak een groep met je broer, voeg de bot toe. Stuur een berichtje in de groep.
Open dan in je browser:

```
https://api.telegram.org/bot<JOUW_TOKEN>/getUpdates
```

Zoek `"chat":{"id":-1001234567890`. Dat negatieve getal is je chat-id.

**3. Secrets invullen**

In deze repo: **Settings → Secrets and variables → Actions → New repository secret**

| Naam | Waarde |
|---|---|
| `TELEGRAM_BOT_TOKEN` | het token van BotFather |
| `TELEGRAM_CHAT_ID` | het negatieve groepsnummer |

**4. Actions aanzetten**

Tab **Actions** → inschakelen. Draai **Surf check** een keer handmatig met
`dry_run` aan: dan zie je in het log precies wat het zou sturen, zonder dat
er iets in de groep valt.

---

## Hoe het beslist

**Per uur** wordt gekeken naar hoogte, periode, wind en deiningsrichting.
Elk van die vier is een harde eis — val je op één af, dan telt het uur niet.
Wat overblijft krijgt een score van 0-100.

**Per dag** telt alleen het ochtendvenster (06:00-11:00 lokaal). Er moeten
minstens drie aaneengesloten goede uren in zitten. Dit is bewust zo: aan de
kust trekt de thermische zeewind bijna dagelijks rond elf uur aan. Zou je
eisen dat de wind de hele dag onder tien knopen blijft, dan gaat dit ding
vrijwel nooit af.

**Per blok** moeten er genoeg goede dagen op rij zijn: twee voor Frankrijk,
Spanje en Noord-Portugal, drie voor Marokko, Ierland, Engeland en de Algarve.
Verder vliegen betekent meer reisdrag, dus meer dagen nodig.

**Twee alarmniveaus.** Zit de swell 6-9 dagen weg, dan krijg je een vroege
waarschuwing: tickets zijn dan nog betaalbaar, maar de forecast kan draaien.
Komt hij binnen vijf dagen, dan volgt de bevestiging. Zo zie je de prijs
terwijl die laag is, en weet je later of het doorgaat.

Een swell die al gemeld is komt niet nog eens langs, tenzij hij van vroege
waarschuwing naar bevestiging gaat of flink beter is geworden.

### De criteria

| | Waarde |
|---|---|
| Golfhoogte | 5-12 ft brekende golf |
| Periode | minimaal 8s |
| Wind | 0-10kt uit elke richting, of tot 15kt mits offshore |
| Venster | 06:00-11:00 lokaal, minstens 3 uur aaneen |
| Dagen | 2 dichtbij, 3 ver weg |
| Vlucht | maximaal EUR 200 retour p.p. |
| Bed | maximaal EUR 50 per nacht p.p. |

Periode weegt het zwaarst in de score. 8s haalt de drempel, maar komt onderaan
de ranglijst; 14s+ krijgt de volle punten. Zo mis je niets en zie je toch in
één oogopslag of het echte grondzwelling is of windrommel.

---

## Aanpassen

Alles staat in `config.yaml`. Je hoeft nooit in de Python te duiken.

**Een spot toevoegen:**

```yaml
- name: Nieuwe Spot
  region: Portugal
  lat: 39.3450
  lon: -9.3670
  faces: 250          # welke kant de golf op kijkt (graden)
  swell_window: [240, 320]
  size_factor: 1.6    # 1.0 flauw strand · 1.5 point · 1.7 zware reef
  airport: LIS
  drive_min: 75
  tier: near          # near = 2 dagen genoeg, far = 3
  season: [9, 10, 11, 12, 1, 2, 3]
```

`faces` is het belangrijkste getal: daaruit volgt wat offshore is
(namelijk wind uit `faces + 180`).

**Minder meldingen:** zet `min_day_score` omhoog (55 → 65), of
`min_period_s` naar 10.

**Meer meldingen:** `min_day_score` omlaag, of `max_wind_kt` omhoog.

---

## Wat het niet doet

Geen scrapers voor auto's en hostels. Daar bestaat geen gratis, betrouwbare
API voor, en een scraper die stukgaat bij de eerste siteweziging is erger dan
geen scraper. Wat je krijgt is een richtprijs voor de begroting plus een
zoeklink met de datums en het prijsplafond er al in.

Om dezelfde reden staan er geen hostelnamen in de config: die verouderen en
gaan over de kop, en een verkeerde naam in het voorstel is erger dan een
filterlink die altijd klopt.

Vluchtprijzen komen van Ryanair's eigen publieke fare finder. Die dekt
Eindhoven, Weeze, Charleroi en Brussel goed af. Vliegt Ryanair de route niet,
of ligt Transavia lager, dan staat er geen prijs maar wel een Skyscanner-link
die alles meepakt. Beter geen prijs dan een verzonnen prijs.

## Databron

[Open-Meteo](https://open-meteo.com) — gratis, geen sleutel, geen registratie.
Het marine-model voor de deining, het gewone weermodel voor de wind, samen-
gevoegd op tijdstempel. Of de wind offshore is rekent het script zelf uit
op basis van `faces` per spot.

Surfline zit erin als optionele controle achteraf (`confirm_with_surfline`),
maar niet voor de brede scan: dat werkt per spot-id en zou tientallen calls
per run kosten op een endpoint dat daar niet voor bedoeld is.

## Lokaal draaien

```bash
pip install -r requirements.txt
python main.py --dry-run --verbose    # echte forecast, niets versturen
python main.py --demo --dry-run       # verzonnen swell, bericht bekijken
python tests/test_logic.py            # 31 controles op de beslislogica
```
