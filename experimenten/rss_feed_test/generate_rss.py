"""
Proof-of-concept: genereert een RSS 2.0-feed met dezelfde structuur als
https://hzindustrial.ijzersterk.nl/ck/front/objecten/rss.asp?user_id=1009

Gebruikt volledig fictieve testdata. Staat los van de hoofdpipeline
(blueprints/ en systems/) en heeft geen koppeling met klantdata of het dashboard.
"""

from datetime import datetime, timedelta

TEST_POSTS = [
    {
        "id": 1,
        "title": "Nieuwe showroom geopend",
        "intro": "intro",
        "hashtags": "#showroom #nieuw",
        "description": (
            "Vandaag openden we onze vernieuwde showroom! 🎉\n\n"
            "Kom langs en bekijk ons volledige assortiment in het echt. "
            "Ons team staat klaar om je vrijblijvend te adviseren.\n\n"
            "🌐 www.testbedrijf-acme.nl"
        ),
        "weblog": "tekst",
        "picture": "https://example.com/test-images/showroom.jpg",
        "link": "https://www.testbedrijf-acme.nl/showroom",
        "pub_date": datetime(2026, 6, 12, 9, 0, 0),
    },
    {
        "id": 2,
        "title": "Tip van de week",
        "intro": "intro",
        "hashtags": "#tips #onderhoud",
        "description": (
            "Wist je dat regelmatig onderhoud de levensduur van je apparatuur "
            "aanzienlijk verlengt? ⚙️\n\n"
            "Onze monteurs delen graag hun beste tips — vraag ernaar bij je "
            "volgende bezoek.\n\n"
            "🤝 Samen werken aan duurzaam gebruik."
        ),
        "weblog": "",
        "picture": "https://example.com/test-images/onderhoud.jpg",
        "link": "https://www.testbedrijf-acme.nl/tips",
        "pub_date": datetime(2026, 6, 11, 14, 30, 0),
    },
    {
        "id": 3,
        "title": "Klant in de spotlight",
        "intro": "intro",
        "hashtags": "#klantverhaal #succes",
        "description": (
            "Deze week zetten we een trouwe klant in het zonnetje! ☀️\n\n"
            "Bedankt voor het vertrouwen en de fijne samenwerking de afgelopen "
            "jaren. Op naar nog veel meer mooie projecten samen.\n\n"
            "🌐 www.testbedrijf-acme.nl/cases"
        ),
        "weblog": "",
        "picture": "https://example.com/test-images/klant.jpg",
        "link": "https://www.testbedrijf-acme.nl/cases/klant-spotlight",
        "pub_date": datetime(2026, 6, 10, 11, 15, 0),
    },
    {
        "id": 4,
        "title": "Achter de schermen",
        "intro": "intro",
        "hashtags": "#behindthescenes #team",
        "description": (
            "Een kijkje achter de schermen bij Testbedrijf Acme! 👀\n\n"
            "Ons team werkt hard aan de voorbereidingen voor een groot "
            "nieuw project. Volg ons om op de hoogte te blijven van de "
            "voortgang.\n\n"
            "🌐 www.testbedrijf-acme.nl"
        ),
        "weblog": "",
        "picture": "https://example.com/test-images/team.jpg",
        "link": "https://www.testbedrijf-acme.nl/over-ons",
        "pub_date": datetime(2026, 6, 9, 16, 0, 0),
    },
    {
        "id": 5,
        "title": "Vacature: monteur gezocht",
        "intro": "intro",
        "hashtags": "#vacature #werken",
        "description": (
            "We zoeken versterking! 🔧\n\n"
            "Ben jij een gedreven monteur en wil je werken bij een "
            "groeiend bedrijf met korte lijnen en veel ruimte voor eigen "
            "inbreng? Solliciteer vandaag nog.\n\n"
            "🌐 www.testbedrijf-acme.nl/vacatures"
        ),
        "weblog": "",
        "picture": "https://example.com/test-images/vacature.jpg",
        "link": "https://www.testbedrijf-acme.nl/vacatures/monteur",
        "pub_date": datetime(2026, 6, 8, 8, 45, 0),
    },
]


def _fmt(dt: datetime) -> str:
    return f"{dt.day}-{dt.month}-{dt.year} {dt.strftime('%H:%M:%S')}"


def build_rss(posts: list[dict]) -> str:
    last_build = max(p["pub_date"] for p in posts)

    items = []
    for p in posts:
        items.append(f"""
		<item>
		    <id><![CDATA[{p['id']}]]></id>
		    <title><![CDATA[{p['title']}]]></title>
		    <intro><![CDATA[{p['intro']}]]></intro>
		    <hashtags><![CDATA[{p['hashtags']}]]></hashtags>
		    <description><![CDATA[{p['description']}]]></description>
		    <weblog><![CDATA[{p['weblog']}]]></weblog>

		    	<picture>{p['picture']}</picture>
		    	<enclosure type="image/jpeg" url="{p['picture']}" />

		    <link><![CDATA[{p['link']}]]></link>
		    <pubDate>{_fmt(p['pub_date'])}</pubDate>
		</item>""")

    return f"""<?xml version="1.0" encoding="UTF-8" ?>

	<rss version="2.0">
		<channel>
			<title>Sociale stream van Testbedrijf Acme (testdata)</title>
			<link></link>
			<description></description>
			<lastBuildDate>{_fmt(last_build)}</lastBuildDate>
{''.join(items)}
		</channel>
	</rss>
"""


if __name__ == "__main__":
    xml = build_rss(TEST_POSTS)
    out_path = "rss.xml"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Geschreven: {out_path} ({len(TEST_POSTS)} testposts)")
