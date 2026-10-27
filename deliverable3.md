Steg 3 – Diligence: Utvärdera och dokumentera
----------------------------------------------------------------------------------
Jag gav den kontextet av ett exempel som jag själv kört, ett test jag körde i venv där jag lade in flera versioner av samma input options, i detta fallet flera --from och flera --to.
Detta bör inte ske då det är missvissande att ta in och tillåta flera versioner av samma input variabel, som i detta fall är 2 datum som ska utgöra ett intervall.
Jag frågade den varför den koden valde den specifika --from variabeln som den valde och vad som skulle kunna göras för det.
Agenten gav mig 3 hypoteser eftersom jag frågade efter 3, den jag valde var mest trolig efter min egen erfarnhet och förståelse av hur python fungerar när den hanterar input data.
Det kändes som att den hade bestämt sig för den första och gav mig 3 bara för att jag frågade efter dem, då hypotes 2 är utesluten från början och hypotes 3 är en generell, "du kanske körde på fel ställe med fel kod".

Hypoteserna:
-------------------------------------------------------------------------------------------------------------
Hypoteser, mest sannolik först

1. Click skriver över värdet varje gång optionen dyker upp (bekräftad)

Mekanism: --from/--to deklareras i src/jira_activity/cli.py som vanliga typer.Option utan multiple=True. Då får de action "store" i parsern. Typer 0.27.3 har en egen kopia av Click (typer._click.parser), och där gör _Option.process så här:

if self.action == "store":
    state.opts[self.dest] = value   # skriver över det förra värdet utan kontroll

Det finns ingen räknare och ingen kontroll av dubbletter. Varje förekomst skriver över den förra i en dict, så den sista vinner och inget fel uppstår. Click gör så med flit, så att man kan skriva över ett värde senare på kommandoraden, till exempel i alias.

Verifiering (gjord):
- Jag läste källkoden med inspect.getsource(typer._click.parser._Option.process). Den visar raden ovan.
- Jag körde CliRunner med run_report mockad. Den fick ('2026-10-01', '2026-10-28') och exit 0.
- Ett extra test kan bekräfta det: --from A --from B ska alltid ge B, oavsett ordning mot --to.

2. Vår egen kod väljer bland flera värden, till exempel min eller max

Mekanism: Man skulle kunna tro att parse_period/DateRange.from_dates får en lista och väljer ett av värdena.

Verifiering: Den här hypotesen är i praktiken utesluten.
- ReportOptions.from_date har typen str, inte en lista.
- Värdena stämmer inte med min eller max. Minsta --from vore 09-23 och största 10-22, men resultatet blev 10-01, alltså det sista.
- För att vara helt säker: sätt en brytpunkt eller print i parse_period och se att den bara får en sträng.

3. En annan installation av CLI:t än repots kod körs

Mekanism: jira-activity ligger inte på systemets PATH, bara i .venv. Om du kör en annan iäldre pipx-version eller en annan Typer- eller Click-version, kan beteendet kommadärifrån. Men alla Click-versioner har samma regel om att sista värdet vinner, så den här hypotesen förklarar inte felet. Den handlar bara om att säkerställa att du testar rätt kod.

Verifiering:
- Kolla vilken exe som körs med Get-Command jira-activity.
- Kolla versionen med .venv\Scripts\python -c "import typer; print(typer.__version__, typer.__file__)".
- Kör samma kommando med .venv\Scripts\jira-activity och jämför resultatet.

----------------------------------------------------------------------------------------------------------------

Felet är tydligt att det är hanteringen av inparametrarna i cli.py som är felet, agenten hittade det snabbt och var tydlig att det är där felet låg
Det jag tycker den skulle kunna vara lite tydligare med är att skriva t.ex "Endast en hypotest är trolig" och inte hitta på omöjliga hypoteser som ej är baserat på koden,
detta kan leda en fel om man inte har någon koll på koden som analyseras
Så båda de andra hypoteserna som den gav var helt fel.
