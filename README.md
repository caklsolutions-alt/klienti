# Klientské zóny – Sebastian Cakl

Web na adrese https://klienti.sebastiancakl.cz. Data každé zóny jsou šifrovaná (AES-GCM) a otevře je jen osobní odkaz klienta s klíčem. Aktualizuje se automaticky dvakrát denně.

Ikony sítí: Font Awesome Free (CC BY 4.0).

Odpovědi klientů ze zón (pořadí videí, potvrzení nebo jiný termín natáčení) zóna zašifruje klíčem klienta a uloží napřímo přes Google formulář „CRM – zápis ze zón“. Automatická kontrola je čte z tabulky odpovědí a promítá do CRM (`tools/zone_inbox.py`).
