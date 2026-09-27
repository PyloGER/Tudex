# Changelog

## 1.6.0-beta.8
- Mullvad: Kontonummer ist jetzt **komplett verdeckt**; das Auge daneben blendet sie ein und wieder aus.
- Backup → Fortschritt: Statusfeld je Ziel passt sich dem Text an (war fest 120 px breit); Tempo lesbar als „16.45 MB/s“.

## 1.6.0-beta.7
- Taskmanager → Leistung: **Kacheln anklicken für Details** (live, alle 2 s; erneut klicken oder „Schließen“ blendet aus):
  - **Prozessor**: Geschwindigkeit, Temperatur, Betriebszeit, Prozesse/Threads/Handles, Last; Modell, Basis- und Maximaltakt, Sockel, Kerne, virtuelle Prozessoren, Virtualisierung (KVM / AMD-V / VT-x), virtuelle Maschine, L1/L2/L3-Cache, CPUfreq-Treiber und -Regler, Energiemodus, Boost.
  - **Arbeitsspeicher**: in Verwendung, verfügbar, zugesichert, im Cache, Swap, zram komprimiert/Ersparnis; Takt (MT/s), belegte Steckplätze, Formfaktor, Typ (z. B. LPDDR5).
  - **Datenträger** (Auswahl je Laufwerk): Lese-/Schreibtempo, aktive Zeit, Antwortzeit, Summen seit Start, Temperatur; Modell, Kapazität, formatiert, Systemdatenträger, Typ, WWN, Seriennummer, Partitionen mit Belegung.
  - **Grafik** (Auswahl je Karte): Auslastung, Takt, Leistungsaufnahme, VRAM, Speichertakt, Video kodieren/dekodieren (NVIDIA), Temperatur, Lüfter; Treiber, OpenGL-/Vulkan-Version, PCIe-Geschwindigkeit, PCI-Adresse.
  - **Netzwerk** (je Schnittstelle), **Akku** (Zyklen, Zustand, Spannung, Ladegrenze), **Swap** (Geräte, Priorität, Swappiness) und **System & Lüfter** (Drehzahlen aller Lüfter, Temperaturen, Kernel, Startzeit).
- Alles ohne root; Werte, die das System nicht meldet, stehen als „—“.

## 1.6.0-beta.6
- **Pop-ups überarbeitet**: kein schwarz hinterlegter Text mehr in Hinweis-, Warn- und Rückfrage-Fenstern (trat unter KDE auf).
- Flache Symbole in den Tuxdex-Farben statt der Symbole des System-Themes; Buttons in allen Pop-ups im Tuxdex-Stil (Hauptaktion farbig, Abbrechen links, Aktion rechts), mehr Innenabstand.
- Verschlüsseltes Backup wiederherstellen: Passwort-Abfrage im Tuxdex-Stil und auf Deutsch statt des englischen Standardfensters.

## 1.6.0-beta.5
- Taskmanager → **Autostart**:
  - Autostart-Programme per Schalter an/aus, eigene Einträge entfernen, installierte Programme hinzufügen. System-Einträge bleiben unangetastet – Tuxdex legt nur eine eigene Einstellung in `~/.config/autostart` an.
  - Hintergrunddienste des Benutzers (`systemd --user`) an/aus.
  - **Bootzeit**: Dauer des letzten Starts, aufgeteilt in Firmware, Bootloader, Kernel, Initramfs und Dienste, dazu die langsamsten Dienste. Bekannte Bremsen wie `NetworkManager-wait-online` lassen sich per Knopf deaktivieren.

## 1.6.0-beta.4
- Taskmanager: **Prozesse nach Programm gruppiert** – jedes Programm ist ein aufklappbarer Ordner mit Summe für CPU, Arbeitsspeicher und Datenträger (z. B. „Spotify (3)“). „Alle beenden“ / „Alle erzwingen“ beendet alle Prozesse eines Ordners auf einmal, auch Priorität gilt für alle. Aufgeklappte Ordner bleiben beim Aktualisieren offen; abschaltbar über „Nach Programm gruppieren“.

## 1.6.0-beta.3
- **Weniger RAM**: Tabs werden erst beim ersten Öffnen gebaut und nach 5 Minuten ohne Nutzung wieder abgebaut (nie während ein Scan, Backup oder Befehl läuft). Freigegebener Speicher geht ans System zurück. Start: ~83 statt ~118 MB.
- **Keine verwaisten Scans mehr**: Beim Schließen oder Neustart beendet Tuxdex alle gestarteten Hintergrundprozesse (vorher Rückfrage, wenn noch etwas läuft). Läuft beim Start noch ein Virenscan oder Backup aus einer früheren Sitzung, bietet Tuxdex an, ihn zu beenden.
- Taskmanager: root-Prozesse, die Tuxdex gestartet hat, heißen jetzt z. B. „clamscan · gestartet von Tuxdex“ – ihr Speicher wird nicht mehr Tuxdex selbst zugerechnet.
- Software-Liste: Tooltips nur noch in der Beschreibungsspalte (weniger Speicher bei vielen Paketen).

## 1.6.0-beta.2
- Vollversion/Beta als Umschalter mit Versionsanzeige (aus 1.5.6).

## 1.6.0-beta.1
- **Neues Modul „Backup“**:
  - Mehrere Ziele gleichzeitig (USB-Platten, interne Laufwerke, Ordner) – jedes mit eigenem Fortschritt, Tempo und Restzeit.
  - **Snapshots**: jede Sicherung eine eigene Version, unveränderte Dateien kosten keinen Platz (Hardlinks, wie Time Machine).
  - **Spiegel**: 1:1-Kopie, überträgt nur Änderungen.
  - **Archiv**: komprimiert mit zstd, xz oder gzip (3 Stärken), optional mit Passwort (AES-256). Wird einmal gepackt und parallel auf alle Ziele geschrieben, mit Prüfsumme und Prüfung nach dem Schreiben. Auf FAT32 automatisch in 4-GB-Teile geteilt.
  - Ausnahmen (z. B. `~/.cache`), Versionen behalten (3–50), root-Modus für Systemordner.
  - Vorhandene Backups je Ziel anzeigen, öffnen, löschen und wiederherstellen – in einen Ordner oder an den Originalort.
  - Zeitplan täglich/wöchentlich per systemd-Timer (`tuxdex --backup`), läuft auch ohne Fenster und holt verpasste Termine nach.
- Taskmanager → System: **Versionsstand** von Grafiktreiber (NVIDIA/Mesa/Vulkan), CPU-Microcode, Mainboard/BIOS (mit Alter), Kernel und Firmware (fwupd) – inkl. „Update da“ und „Neustart nötig“.
- Sicherheit: **Leak-Test & VPN-Erkennung** – DNS-Leak-Test, welche DNS-Server Webseiten sehen, ob die IP als VPN (mit Anbieter), Proxy, Tor oder Rechenzentrum erkannt wird, und ob sie auf Sperrlisten steht.
- Sicherheits-Check zeigt einen eingestellten **Proxy** (Umgebungsvariablen, GNOME, KDE).
- Sicherheits-Check zeigt den aktuellen **DNS-Server**: Anbieter (z. B. Router, Cloudflare, Mullvad), Verbindung und ob die Anfragen verschlüsselt (DNS-over-TLS) oder durch den VPN-Tunnel laufen.
- Sicherheits-Check: **Bekannte Sicherheitslücken** über `arch-audit` (optional) – zeigt, welche Pakete ein Update mit Fix haben.
- Mullvad verbunden, aber Kill-Switch aus: Hinweis mit Knopf „Kill-Switch an“.
- Virenscan: Hochrechnung ohne die Ladezeit der Signaturen, dazu voraussichtliches Ende (Uhrzeit) und Gesamtdauer.
- Speicher → „Größen ermitteln“: misst parallel, zeigt jeden Wert sofort und einen Status wie beim Virenscan (läuft/fertig, was gerade gemessen wird, Fortschritt). Ordner, die länger als 2 Minuten brauchen, werden als „zu viele Dateien“ markiert statt alles zu blockieren.

## 1.5.6
- Einstellungen → Aktualisierung: Vollversion/Beta als Umschalter statt Aufklappmenü. Daneben steht, welche Version es jeweils gibt und welche installiert ist.

## 1.5.5
- Einstellungen → Aktualisierung: Auswahl **Vollversion** oder **Beta** – Beta-Versionen bekommen neue Funktionen früher. Zurück zur Vollversion geht jederzeit.

## 1.5.4
- Sicherheits-Check prüft zusätzlich:
  - **CPU-Microcode** (`intel-ucode`/`amd-ucode`) – fehlt er, per Klick installieren.
  - **Swap-Verschlüsselung** – warnt, wenn Swap unverschlüsselt auf der Platte liegt (zram und Swap auf LUKS gelten als sicher).
  - **Kernel-Schutz** – sperrt per Klick kexec und SysRq (`/etc/sysctl.d/90-tuxdex-hardening.conf`), ohne Nachteile im Alltag.

## 1.5.3
- Aktualisierung startet erst nach der Admin-Anmeldung (sudo-Passwort). Ohne Anmeldung wird nichts heruntergeladen oder verändert – gilt für GitHub, Datei und Ordner.
- Neuer Fortschrittsbalken mit Schritt-Anzeige: Dateien laden (x/n), Paket bauen, prüfen, installieren, fertig. Bei Fehlern zeigt er, an welcher Stelle es hakt.

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
