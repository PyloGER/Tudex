# Changelog

## 1.4.0
- **Updater** in den Einstellungen: nach Updates auf GitHub suchen (auch automatisch beim Start), Neuerungen anzeigen, per Klick aktualisieren und neu starten.
- Lokal aktualisieren aus einem Archiv (tuxdex-X.Y.Z.tar.gz) oder einem Ordner mit PKGBUILD – Git-Klone werden vorher mit `git pull` aktualisiert.
- Hinweis „Version X verfügbar“ unten rechts in der Statusleiste.

## 1.3.0
- Neuer Tab **Flatpak**: Rechte jeder App per Schalter einstellen (wie Flatseal) – Netzwerk, Dateien, Geräte, Ton/Bildschirm, Umgebungsvariablen, Portal-Freigaben, globale Regeln; riskante Rechte markiert.
- **Software**: Auswahl per Kästchen (kein Strg mehr), Icons, Version, Größe, Quelle/Ort, Installationsdatum, Details mit Abhängigkeiten.
- **ClamAV**: Live-Fortschritt mit Dateien, Datenmenge, Tempo und Restzeit; Status „läuft / arbeitet / hängt?“.
- **Updates**: AUR steht in den Quellen jetzt unten.

## 1.2.0
- Neuer Name: **Tuxdex** (vorher „Arch Linux Manager“ / `arch-manager`). Das Paket ersetzt die alte Version automatisch, gespeicherte Daten und die Quarantäne werden übernommen.
- Offene Ports lassen sich im Tab *Sicherheit* per Knopf sperren oder freigeben (ufw, firewalld).
- Einstellungen (Zahnrad unten links) mit Infos zu Projekt, Autor und Technik.
- ClamAV: sichtbarer Fortschritt beim Laden der Signaturen, Fehler des Download-Servers werden sofort gemeldet.

## 1.0.1
- ClamAV-Signaturen werden bei deutscher Systemsprache korrekt erkannt.

## 1.0.0
- Erste Version als installierbares Paket: Updates, Software, Datenträger, Speicher, Swap, Taskmanager, Antivirus, Sicherheit (Mullvad VPN, Firewall), Benutzer.
