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
waarschuwing. Komt hij binnen vijf dagen, dan volgt de bevestiging.

**Eén bericht per swell.** Een swell wordt onthouden per regio, niet per spot.
Is hij goed op La Gravière, La Piste en Les Bourdaines tegelijk, dan komt er
één bericht met de beste spot en "ook goed in de buurt: ...". Schuift de
forecast een dag op, dan blijft het dezelfde swell. Alleen als hij flink
beter wordt (+12 punten) komt er een update.

**Meldgrens.** Blokken onder score 75 blijven stil; een "Gaan we?"-poll komt
alleen bij 85 of hoger.

### De criteria

| | Waarde |
|---|---|
| Golfhoogte | 5-12 ft brekende golf |
| Periode | minimaal 8s |
| Wind | 0-10kt uit elke richting, of tot 15kt mits offshore |
| Venster | 06:00-11:00 lokaal, minstens 3 uur aaneen |
| Dagen | 2 dichtbij, 3 ver weg |
| Vluchten | alleen direct, vaste routes met richtprijs |
| Bed | maximaal EUR 50 per nacht p.p., gratis annuleren |

---

## Vluchten: vaste routes, geen live zoektocht

Per regio staan in `config.yaml` de directe routes vanuit de Benelux met een
richtprijs (per persoon, retour, alleen rugzak, 3-9 dagen vooruit geboekt).
Het bericht noemt de beste route plus een alternatief, en de knoppen openen
Skyscanner met de datums al ingevuld. Er wordt niets betaald opgezocht.

Beste route = richtprijs plus €20 per uur rijden, zodat een vlucht die drie
uur verderop landt niet wint op een paar tientjes. Heen gaat de dag voor de
eerste goede dag, terug op de avond van de laatste.

Auto, materiaal en bed zijn ook richtprijzen per regio, met een zoeklink.

---

## Opzetten

**1. Telegram-bot** — via `@BotFather`, `/newbot`. Voeg de bot toe aan een
groep, stuur er een bericht dat met `/` begint, en haal het chat-id op via
`https://api.telegram.org/bot<TOKEN>/getUpdates`.

**2. Secrets** — Settings → Secrets and variables → Actions:

| Naam | Waarde |
|---|---|
| `TELEGRAM_BOT_TOKEN` | het token van BotFather |
| `TELEGRAM_CHAT_ID` | het negatieve groepsnummer |

**3. Testen** — Actions → Surf check → Run workflow, met "Testbericht" aan.
Er valt dan een verzonnen voorstel in de groep zodat je ziet dat alles werkt.

---

## Aanpassen

Alles staat in `config.yaml`, met uitleg bovenaan. De knoppen die je het
vaakst nodig hebt:

- **Minder meldingen:** `alerts.min_score` omhoog (75 → 80).
- **Meer meldingen:** `alerts.min_score` omlaag.
- **Poll vaker of minder vaak:** `alerts.poll_min_score`.
- **Vluchtprijs klopt niet meer:** pas `eur` aan bij de route onder de regio.
- **Verder willen rijden:** `max_drive_min` omhoog.

In `stays.yaml` vul je zelf slaapplekken aan waar je geweest bent. Staat er
iets voor de spot waar de swell is, dan zet het voorstel dat erbij in plaats
van alleen een zoeklink.

---

## Databronnen

**[Open-Meteo](https://open-meteo.com)** voor de forecast — gratis, geen
sleutel. Marine-model voor de deining, weermodel voor de wind, samengevoegd
op tijdstempel. Alle spots in één gebundelde aanroep. Of de wind offshore is
rekent het script zelf uit uit de kustorientatie per spot.

**Vluchten worden niet live opgezocht.** Tot september 2026 zocht de bot
via een betaalde Google Flights-scraper, maar elke melding kostte een
zoekopdracht. De directe routes per regio veranderen nauwelijks, dus nu
staan ze vast in de config met een richtprijs (gemeten via Kiwi, okt 2026).

**Auto en bed worden ook niet opgezocht** — daar bestaat geen gratis betrouwbare
bron voor. Je krijgt een richtprijs voor de begroting plus een zoeklink met
datums, coordinaten en prijsplafond er al in.

## Lokaal draaien

```bash
pip install -r requirements.txt
python main.py --dry-run --verbose    # echte forecast, niets versturen
python main.py --demo --dry-run       # verzonnen swell, bericht bekijken
python test_logic.py                  # 60 controles op de beslislogica
```
