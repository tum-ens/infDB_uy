# InfDB Uruguay – Zusammenfassung

*Stand Oktober 2026 · [English](tldr.md) · Deutsch · [Español](tldr.es.md) · Start: `docker compose up --build`, dann <http://localhost:8050>.*

## Ziel und Stand

**Ziel.** Die InfDB-Pipeline auf Uruguay anwenden, beginnend mit **Cordón**, einem 228 ha großen Stadtviertel (barrio) von Montevideo.

**Erledigt:**

- Bestandsaufnahme der offenen Daten Uruguays und ihre Zuordnung zu den InfDB-Eingangsdaten
- eine Pipeline, die die Daten für Cordón ohne Modellannahmen herunterlädt und aufbereitet
- ein Web-Explorer für diese Daten

**Noch nicht erledigt:** die eigentliche InfDB-Anpassung (Gebäude aus LiDAR, Attributzuordnung, Bevölkerungsverteilung).

## Unterschiede zu den deutschen InfDB-Eingangsdaten

| InfDB-Eingang (DE) | Uruguay | Bewertung |
|---|---|---|
| LoD2-CityGML-Gebäude | **Keine offene Gebäudegeometrie.** Montevideo hat eine offene LiDAR-Befliegung 2024 (klassifiziert, Gebäudeklasse 6). Sonst: Google Open Buildings 2.5D, IDE-Oberflächenmodelle 2017–18, OSM. | Hauptlücke. Grundrisse und Höhen müssen abgeleitet werden. |
| Baujahr, Geschosse, Geschossfläche aus Zensus-Gitter und Geometrie geschätzt | **Im Kataster beobachtet.** Die DNC veröffentlicht monatlich und landesweit jede *línea de construcción*: Geschoss, Nutzung, Kategorie, Zustand, Dachart, m², Baujahr, ursprüngliches Baujahr umgebauter Teile. | Besser. Die InfDB-SQL-Schritte 05 und 09 werden zu Nachschlagen statt Schätzen. |
| Zensus 100-m-Gitter | Zensus 2023 je Zensuszone (13.648 Polygone, nur Montevideo) oder Segment (landesweit). Gewichtete Mikrodaten mit Heizenergieträger, Klimaanlagen und Solarthermie je Segment, nach Annahme der INE-Nutzungsbedingungen. | Polygone statt Gitter. Energievariablen, die InfDB fehlen. |
| BKG-Verwaltungsgrenzen / AGS | Codes von INE und DNC, die sich unterscheiden (`01`/`01020` vs. `V`/`AA`); eine Zuordnungstabelle ist nötig. | Anpassen |
| basemap.de-Straßen, PLZ | Straßenachsen der Stadt sowie Hausnummernpunkte mit Padrón (Flurstücksnummer) und Straßenabschnitt, also eine fertige Gebäude→Straße-Zuordnung. PLZ entfällt. | In Montevideo gleichwertig |
| TABULA-Typologie | Keine. Aufbau aus DNC-Kategorie × Dach × Baujahr plus Baustoffen aus dem Zensus. | Lücke |
| pylovo-Netzparameter | Keine Daten des Netzbetreibers UTE | Lücke |
| KBS 3035 | Überall EPSG:32721 (UTM 21S). Das LiDAR nutzt EPSG:5382 (SIRGAS-ROU98). | Konfiguration |

**Kurz:** Uruguay hat bessere Gebäude*attribute* als Deutschland, aber keine Gebäude*geometrie*. Die Schätzschritte von InfDB schrumpfen, ein Schritt zur Gebäudeableitung aus LiDAR kommt hinzu. Details (Englisch): [Vergleich](infdb-comparison.md), [nötige Änderungen](required-changes.md).

## Pilot Cordón: geprüfte Ergebnisse

**Datenumfang:**

- 5.130 Flurstücke und 27.802 Katastereinheiten
- 147.823 Gebäudeteile (*líneas*)
- 287 Zensuszonen, die das Viertel berühren (186 vollständig innerhalb, 35.591 Einwohner)
- 8 LiDAR-Kacheln (164 Mio. Punkte, 1,2 GB)

**Massendaten des Katasters vs. amtliche Katasterauszüge (PDF).** Verglichen mit 100 Auszügen (*cédulas catastrales*) vom Webdienst des Katasters:

- 99 stimmen exakt überein, in jedem Gebäudeteil, jeder Fläche, jedem Baujahr, jeder Kategorie, jedem Zustand und Wert sowie im Wertverlauf über 4 Jahre.
- Die eine Abweichung (V-AA-137) ist ein Umbau von 2015, der im live erzeugten Auszug steht, aber nicht im September-Massenexport.
- Das Auslesen von PDFs ist daher nicht nötig.

**Verknüpfung.** 99,9 % der Flurstücke Montevideos haben ein Polygon. In Cordón passen Flurstücks- und Hausnummernschlüssel bis auf 8 Flurstücke zusammen.

**Reproduzierbarkeit.** Ein frisches `docker compose up --build` lädt alles herunter (≈ 1,5 GB) und startet das Dashboard in etwa 9 Minuten. Rohdateien sind mit SHA-256 in einem Manifest erfasst.

## Befunde, die vor der Modellierung eine Entscheidung brauchen

1. **Gebäudeteile zweier Régimen auf einem Flurstück.** 917 Flurstücke haben Teile sowohl im *régimen común* (CO, normales Eigentum) als auch in der *propiedad horizontal* (PH, Wohnungseigentum), typischerweise während einer Umwandlung. 40.512 Teile (1,1 Mio. m², 23 % der Fläche) gehören zu einem Régimen ohne Einheitseintrag. Die Summe aller Teile zählt diese Gebäude doppelt.
2. **Drei „bebaute Flächen“ weichen voneinander ab.** Alle Teile ergeben 4,79 Mio. m², Teile bestehender Régimen 3,68 Mio. m², die bebaute Fläche der Einheiten selbst 3,07 Mio. m². Die Teile enthalten auch Mauern, Treppenpodeste und Freiflächen. Welche Definition speist InfDBs `floor_area`?
3. **Datenqualität.** 581 Teile haben das Baujahr 0, 22.301 haben 0 m², und 16.460 sind *a construir* (noch nicht gebaut). Manche Codes haben keine Bezeichnung in der DNC-Codetabelle (z. B. Dachcode 5 bei 6.252 Teilen).
4. **LiDAR.** Die Kacheln sind in EPSG:5382 und enthalten Klassen (11, 13, 15, 24, 105, 120, 121), die die Stadt nicht dokumentiert.
5. **Zensuszonen** am Rand des Viertels enthalten weitere 18.471 Einwohner. Wie sie zugerechnet werden, ist eine Modellentscheidung.

All das wird im Dashboard berichtet, markiert und ist filterbar, aber **nicht aufgelöst**. Nach der Regel der Pipeline bleiben die Rohdaten unverändert.

## Nächste Schritte (Vorschlag)

1. Gebäudegrundrisse und -höhen aus dem LiDAR ableiten (DGM, nDOM, Grundrisse an Flurstücksgrenzen geteilt).
2. Regeln für die Befunde 1, 2 und 5 festlegen, dann die InfDB-SQL-Schritte 00, 02 und 05–13 über einen Länderschalter anpassen.
3. Die ANDA-Nutzungsbedingungen des INE annehmen (gewichtete Zensus-Mikrodaten). Die Einlese-Pipeline ist fertig und an Beispieldateien getestet.
4. Eine uruguayische Gebäudetypologie für ro-heat entwerfen. Beim Netzbetreiber UTE nach Netzdaten für pylovo fragen.
5. Von Cordón auf Viertel mit Einfamilienhäusern (Carrasco) und informellen Siedlungen (Casavalle) erweitern, dann auf ganz Montevideo.
