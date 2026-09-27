# Changelog

## 1.5.2
- VPN-Erkennung korrigiert: Eine pausierte oder gestoppte Verbindung (z. B. `tailscale down`) gilt nicht mehr als „verbunden“, auch wenn die Schnittstelle noch existiert.
- Tailscale wird über seinen Status erkannt: ohne Exit-Node als „Tailscale an“ (Internet läuft direkt), mit Exit-Node als aktives VPN.
- Andere VPNs (WireGuard, OpenVPN …) zählen nur mit Adresse; Split-Tunnel wird erkannt und angezeigt.
- Der VPN-Status im Tab „Sicherheit“ aktualisiert sich alle 10 Sekunden.

## 1.5.1
- Beim Start sucht Tuxdex automatisch nach **System-Updates** (pacman, AUR, Flatpak). Die Anzahl erscheint am Tab „Updates“ und unten rechts – rot, wenn wichtige Updates dabei sind; ein Klick öffnet den Tab.
- Einstellungen → System-Updates: automatische Prüfung beim Start an/aus. Installiert wird weiterhin nur auf Klick.

## 1.5.0
- Beim Start sucht Tuxdex automatisch nach Updates und bietet eine neue Version in einem Fenster an – mit den Neuerungen und „Jetzt aktualisieren“ / „Später“.
- Einstellungen → Aktualisierung: automatische Prüfung beim Start an/aus, Update-Fenster an/aus (sonst nur Hinweis unten rechts).
- ClamAV und Mullvad VPN sind rein optional: Tuxdex bietet keine Installation und keine Links mehr an. Fehlen sie, zeigt der Bereich nur einen neutralen Hinweis.

## 1.4.2
- Updater erkennt neue Versionen sofort: Tuxdex fragt den neuesten Commit direkt ab, statt die bis zu 5 Minuten zwischengespeicherten Dateien von raw.githubusercontent.com zu lesen.
- Update über GitHub lädt die Paketdateien gezielt vom neuesten Commit (robuster als das Archiv).
- Neuerungen im Updater zeigen `Code` und Sonderzeichen korrekt an.

## 1.4.1
- Update-Quelle ist fest auf github.com/PyloGER/Tuxdex eingestellt – der Updater findet neue Versionen jetzt ohne Einrichtung.
- Einstellungen: Autor PyloGER, Unternehmen Voxellab, Kontakt contact@voxellab.de, Link zur Projektseite, Hinweis „AI made – mit Claude“.
- Pfade im Home-Ordner werden als `~/…` angezeigt – ohne Benutzernamen.

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
