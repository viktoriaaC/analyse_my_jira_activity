Prjektet ska via Jiras api:er anropa JIRA för en jira site som användaren har tillåtelse att lägga upp api nycklar i
Via CLI:et ska man kunna lägga in sin api nyckel och jira sida, datum intervall, sedan få en visuell representation på var tickets legat i för statusar under tidsperioden,
Också vilka tickets som varit i vilket status under intervallet

Vald teknikstack och varför
Valt python för att lätt kunna installera CLI:et och kunna potentiellt skalas till att både vara CLI och hemsida

Arkitekturprinciper du vill följa (till exempel: "inga globala variabler", "all I/O sker i ett lager", "funktioner ska göra en sak")
All I/O ska ske i ett lager, 
alla externa anrop ska ha en tydlig felhantering, hantera alla exceptions med unika fel meddelanden
Tydlig beskrivning av hur användandet av CLI ska gå till,
funktioner ska göra en sak, 

Saker agenten INTE ska göra (till exempel: "byt inte databas", "lägg inte till externa beroenden utan att fråga")
Lägg inte till externa beroende utan att fråga, 
spara ej ner data utan att bli tillfrågad, 
logga ej anrop förutom det som är specifierat i utils/logger.py,
Ändra ej CLI utan att fråga , inparametrar eller utparametrar då det kan påverka användaren
Arbeta endast i feature brancher, master får endast uppdateras via PR godkända av repots ägare


