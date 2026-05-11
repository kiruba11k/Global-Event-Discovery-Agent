"""
Seed connector — curated high-quality B2B events.
IMPORTANT: All dates are 2026/2027 so they are never purged by purge_past_events().
This file is the guaranteed DB baseline. Seed events are tagged
source_platform='Seed' and are explicitly excluded from purge logic.

Current date reference: May 2026.
All events dated from June 2026 onwards.
"""
import uuid, hashlib
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from loguru import logger


def _h(name, date_val, city):
    raw = f"{name.lower().strip()}|{date_val}|{city.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _ev(**kw) -> EventCreate:
    kw.setdefault("id",               str(uuid.uuid4()))
    kw.setdefault("dedup_hash",       _h(kw["name"], kw["start_date"], kw.get("city", "")))
    kw.setdefault("description",      "")
    kw.setdefault("short_summary",    "")
    kw.setdefault("edition_number",   "")
    kw.setdefault("end_date",         kw["start_date"])
    kw.setdefault("duration_days",    1)
    kw.setdefault("venue_name",       "")
    kw.setdefault("address",          "")
    kw.setdefault("country",          "")
    kw.setdefault("is_virtual",       False)
    kw.setdefault("is_hybrid",        False)
    kw.setdefault("est_attendees",    500)
    kw.setdefault("vip_count",        0)
    kw.setdefault("speaker_count",    0)
    kw.setdefault("category",         "conference")
    kw.setdefault("industry_tags",    "tech")
    kw.setdefault("audience_personas","executives,professionals")
    kw.setdefault("ticket_price_usd", 0.0)
    kw.setdefault("price_description","See website")
    kw.setdefault("registration_url", "")
    kw.setdefault("source_url",       "")
    kw.setdefault("source_platform",  "Seed")
    kw.setdefault("sponsors",         "")
    kw.setdefault("speakers_url",     "")
    kw.setdefault("agenda_url",       "")
    return EventCreate(**kw)


SEED_EVENTS = [

    # ══════════════════════════════════════════════════════
    # AI / TECH
    # ══════════════════════════════════════════════════════
    _ev(
        name="AI Summit Singapore 2026",
        start_date="2026-09-10", end_date="2026-09-11",
        city="Singapore", country="Singapore",
        est_attendees=3500, vip_count=150, speaker_count=80,
        category="summit",
        industry_tags="AI,machine learning,tech,cloud,data",
        audience_personas="CTO,CIO,Head of AI,CDO,VP Engineering,startup founder,investor",
        description="Southeast Asia's premier AI summit for enterprise leaders, researchers, and builders.",
        ticket_price_usd=1200.0, price_description="From $1,200",
        registration_url="https://www.theaisummit.com/singapore",
        source_url="https://www.theaisummit.com/singapore",
    ),
    _ev(
        name="TechCrunch Disrupt 2026",
        start_date="2026-10-27", end_date="2026-10-29",
        city="San Francisco", country="USA",
        est_attendees=10000, vip_count=500, speaker_count=200,
        category="conference",
        industry_tags="startup,venture capital,tech,AI,product,SaaS",
        audience_personas="startup founder,investor,CTO,CEO,VP Engineering,developer",
        description="The world's leading startup conference.",
        ticket_price_usd=3000.0, price_description="From $3,000",
        registration_url="https://techcrunch.com/events/tc-disrupt-2026/",
        source_url="https://techcrunch.com/events/",
    ),
    _ev(
        name="Cloud Expo Asia 2026",
        start_date="2026-10-07", end_date="2026-10-08",
        city="Singapore", country="Singapore",
        est_attendees=8000, vip_count=200, speaker_count=150,
        category="expo",
        industry_tags="cloud computing,tech,SaaS,digital transformation,cybersecurity,AI",
        audience_personas="CIO,CTO,IT director,cloud architect,VP Engineering,CISO",
        description="Asia's most comprehensive cloud computing and digital infrastructure expo.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.cloudexpoasia.com/",
        source_url="https://www.cloudexpoasia.com/",
    ),
    _ev(
        name="AWS re:Invent 2026",
        start_date="2026-11-30", end_date="2026-12-04",
        city="Las Vegas", country="USA",
        est_attendees=50000, vip_count=1000, speaker_count=400,
        category="conference",
        industry_tags="cloud computing,AWS,tech,developer,SaaS,AI,machine learning",
        audience_personas="cloud architect,developer,CTO,CIO,VP Engineering,Head of Data",
        description="Amazon Web Services annual conference — the world's largest cloud computing event.",
        ticket_price_usd=2100.0, price_description="From $2,100",
        registration_url="https://reinvent.awsevents.com/",
        source_url="https://reinvent.awsevents.com/",
    ),
    _ev(
        name="Google Cloud Next 2026",
        start_date="2026-09-16", end_date="2026-09-18",
        city="Las Vegas", country="USA",
        est_attendees=30000, vip_count=800, speaker_count=300,
        category="conference",
        industry_tags="cloud computing,AI,Google Cloud,tech,machine learning,data",
        audience_personas="cloud architect,developer,CTO,CIO,CDO,VP Engineering",
        description="Google Cloud's annual flagship event for AI, data, and cloud innovation.",
        ticket_price_usd=1800.0, price_description="From $1,800",
        registration_url="https://cloud.google.com/next",
        source_url="https://cloud.google.com/next",
    ),
    _ev(
        name="Microsoft Ignite 2026",
        start_date="2026-11-16", end_date="2026-11-20",
        city="Chicago", country="USA",
        est_attendees=30000, vip_count=800, speaker_count=350,
        category="conference",
        industry_tags="tech,cloud,AI,Microsoft,developer,enterprise,SaaS",
        audience_personas="CTO,CIO,cloud architect,developer,VP Engineering",
        description="Microsoft's annual conference for technology professionals and developers.",
        ticket_price_usd=2000.0, price_description="From $2,000",
        registration_url="https://ignite.microsoft.com/",
        source_url="https://ignite.microsoft.com/",
    ),
    _ev(
        name="Web Summit 2026",
        start_date="2026-11-03", end_date="2026-11-06",
        city="Lisbon", country="Portugal",
        est_attendees=70000, vip_count=2000, speaker_count=700,
        category="conference",
        industry_tags="tech,startup,AI,SaaS,venture capital,product,digital",
        audience_personas="CEO,CTO,startup founder,investor,VP engineering,CMO",
        description="One of the world's largest technology conferences attracting 70,000+ attendees.",
        ticket_price_usd=1200.0, price_description="From $1,200",
        registration_url="https://websummit.com/",
        source_url="https://websummit.com/",
    ),
    _ev(
        name="CES 2027",
        start_date="2027-01-06", end_date="2027-01-09",
        city="Las Vegas", country="USA",
        est_attendees=130000, vip_count=5000, speaker_count=500,
        category="expo",
        industry_tags="tech,AI,consumer electronics,automotive,healthcare,smart home",
        audience_personas="CEO,CTO,CIO,product head,CMO,investor,startup founder",
        description="The world's most influential technology trade show.",
        ticket_price_usd=0.0, price_description="From $300 (registration)",
        registration_url="https://www.ces.tech/",
        source_url="https://www.ces.tech/",
    ),

    # ══════════════════════════════════════════════════════
    # FINTECH / FINANCE
    # ══════════════════════════════════════════════════════
    _ev(
        name="Singapore FinTech Festival 2026",
        start_date="2026-11-06", end_date="2026-11-08",
        city="Singapore", country="Singapore",
        est_attendees=65000, vip_count=2000, speaker_count=400,
        category="conference",
        industry_tags="fintech,banking,payments,finance,blockchain,AI,insurance",
        audience_personas="CFO,CEO,CTO,head of payments,digital banking leader,investor,VC,fintech founder",
        description="World's largest fintech festival, hosted by MAS.",
        ticket_price_usd=500.0, price_description="From $500",
        registration_url="https://www.fintechfestival.sg/",
        source_url="https://www.fintechfestival.sg/",
        sponsors="MAS,Mastercard,Visa,Google,AWS",
    ),
    _ev(
        name="Money20/20 USA 2026",
        start_date="2026-10-25", end_date="2026-10-28",
        city="Las Vegas", country="USA",
        est_attendees=14000, vip_count=600, speaker_count=250,
        category="conference",
        industry_tags="fintech,payments,banking,finance,digital banking,AI",
        audience_personas="CFO,CEO,CTO,head of payments,digital banking leader,investor",
        description="The world's premier fintech show.",
        ticket_price_usd=4500.0, price_description="From $4,500",
        registration_url="https://us.money2020.com/",
        source_url="https://us.money2020.com/",
    ),
    _ev(
        name="Money20/20 Europe 2027",
        start_date="2027-06-01", end_date="2027-06-04",
        city="Amsterdam", country="Netherlands",
        est_attendees=8000, vip_count=400, speaker_count=200,
        category="conference",
        industry_tags="fintech,payments,banking,finance,regtech,insurtech",
        audience_personas="CFO,CEO,CTO,head of payments,digital banking leader,investor",
        description="Europe's leading fintech conference.",
        ticket_price_usd=3500.0, price_description="From €3,500",
        registration_url="https://europe.money2020.com/",
        source_url="https://europe.money2020.com/",
    ),
    _ev(
        name="India Fintech Forum 2026",
        start_date="2026-09-24", end_date="2026-09-25",
        city="Mumbai", country="India",
        est_attendees=2500, vip_count=100, speaker_count=60,
        category="conference",
        industry_tags="fintech,banking,payments,lending,insurtech,India",
        audience_personas="CFO,CTO,CEO,digital banking leader,payments head,founder,investor",
        description="India's leading fintech conference.",
        ticket_price_usd=300.0, price_description="From ₹25,000",
        registration_url="https://www.indiafintech.com/",
        source_url="https://www.indiafintech.com/",
    ),
    _ev(
        name="Seamless Middle East 2026",
        start_date="2026-09-22", end_date="2026-09-23",
        city="Dubai", country="UAE",
        est_attendees=6000, vip_count=200, speaker_count=100,
        category="conference",
        industry_tags="fintech,payments,ecommerce,retail,digital banking,MENA",
        audience_personas="CFO,CEO,CTO,head of ecommerce,payments director,VP digital",
        description="The Middle East and Africa's leading fintech and e-commerce event.",
        ticket_price_usd=0.0, price_description="Free with registration",
        registration_url="https://seamless-middleeast.com/",
        source_url="https://seamless-middleeast.com/",
    ),

    # ══════════════════════════════════════════════════════
    # HEALTHCARE / MEDTECH
    # ══════════════════════════════════════════════════════
    _ev(
        name="HIMSS Global Health Conference 2027",
        start_date="2027-03-09", end_date="2027-03-13",
        city="Las Vegas", country="USA",
        est_attendees=40000, vip_count=1200, speaker_count=300,
        category="conference",
        industry_tags="healthcare,health IT,digital health,medtech,EHR,AI",
        audience_personas="hospital CIO,healthcare administrator,CDO,health IT director,CMIO",
        description="The global health IT community's most important annual gathering.",
        ticket_price_usd=1850.0, price_description="From $1,850",
        registration_url="https://www.himss.org/global-health-conference",
        source_url="https://www.himss.org/",
    ),
    _ev(
        name="World Health Innovation Summit Singapore 2026",
        start_date="2026-10-13", end_date="2026-10-14",
        city="Singapore", country="Singapore",
        est_attendees=1500, vip_count=80, speaker_count=50,
        category="summit",
        industry_tags="healthcare,digital health,medtech,biotech,AI,wellness",
        audience_personas="hospital CIO,healthcare administrator,health director,investor",
        description="Singapore's leading health innovation summit.",
        ticket_price_usd=800.0, price_description="From $800",
        registration_url="https://whis.sg/",
        source_url="https://whis.sg/",
    ),
    _ev(
        name="Arab Health 2027",
        start_date="2027-01-25", end_date="2027-01-28",
        city="Dubai", country="UAE",
        est_attendees=55000, vip_count=1500, speaker_count=200,
        category="expo",
        industry_tags="healthcare,medtech,pharma,digital health,hospital,Middle East",
        audience_personas="hospital administrator,CIO healthcare,health director,procurement head",
        description="The largest healthcare exhibition in the Middle East.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.arabhealthonline.com/",
        source_url="https://www.arabhealthonline.com/",
    ),
    _ev(
        name="India Health Summit 2026",
        start_date="2026-08-20", end_date="2026-08-21",
        city="Bangalore", country="India",
        est_attendees=3000, vip_count=120, speaker_count=80,
        category="conference",
        industry_tags="healthcare,medtech,digital health,AI,pharma,India",
        audience_personas="hospital CIO,healthcare administrator,health director,startup founder",
        description="India's premier healthcare technology and innovation summit.",
        ticket_price_usd=200.0, price_description="From ₹15,000",
        registration_url="https://www.indiahealthsummit.com/",
        source_url="https://www.indiahealthsummit.com/",
    ),

    # ══════════════════════════════════════════════════════
    # LOGISTICS / SUPPLY CHAIN
    # ══════════════════════════════════════════════════════
    _ev(
        name="Manifest: The Future of Logistics 2027",
        start_date="2027-02-08", end_date="2027-02-10",
        city="Las Vegas", country="USA",
        est_attendees=4000, vip_count=200, speaker_count=100,
        category="conference",
        industry_tags="logistics,supply chain,freight,last mile,tech,AI,fleet",
        audience_personas="supply chain head,COO,VP logistics,fleet manager,procurement head,CTO",
        description="The premier logistics and supply chain innovation conference.",
        ticket_price_usd=2500.0, price_description="From $2,500",
        registration_url="https://www.manifestlasvegas.com/",
        source_url="https://www.manifestlasvegas.com/",
    ),
    _ev(
        name="LogiSYM Asia Pacific 2026",
        start_date="2026-11-11", end_date="2026-11-12",
        city="Singapore", country="Singapore",
        est_attendees=1200, vip_count=60, speaker_count=40,
        category="conference",
        industry_tags="logistics,supply chain,freight,shipping,ASEAN,trade",
        audience_personas="supply chain head,COO,VP logistics,fleet manager,procurement head",
        description="Asia Pacific's supply chain and logistics leadership conference.",
        ticket_price_usd=900.0, price_description="From $900",
        registration_url="https://www.logisym.com/",
        source_url="https://www.logisym.com/",
    ),
    _ev(
        name="India Warehousing Show 2026",
        start_date="2026-08-19", end_date="2026-08-21",
        city="New Delhi", country="India",
        est_attendees=6000, vip_count=150, speaker_count=60,
        category="expo",
        industry_tags="logistics,warehousing,supply chain,manufacturing,intralogistics",
        audience_personas="supply chain head,COO,warehouse manager,procurement head,fleet manager",
        description="India's dedicated warehousing and intralogistics exhibition.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.indiawarehousingshow.com/",
        source_url="https://www.indiawarehousingshow.com/",
    ),
    _ev(
        name="Transport Logistic Munich 2027",
        start_date="2027-06-08", end_date="2027-06-11",
        city="Munich", country="Germany",
        est_attendees=70000, vip_count=2000, speaker_count=300,
        category="expo",
        industry_tags="logistics,supply chain,transport,freight,air cargo,shipping",
        audience_personas="supply chain head,COO,VP logistics,fleet manager,procurement head",
        description="The world's leading trade fair for logistics, mobility, IT, and supply chain management.",
        ticket_price_usd=0.0, price_description="See website",
        registration_url="https://www.transportlogistic.de/",
        source_url="https://www.transportlogistic.de/",
    ),

    # ══════════════════════════════════════════════════════
    # SaaS / PRODUCT / STARTUP
    # ══════════════════════════════════════════════════════
    _ev(
        name="SaaStr Annual 2026",
        start_date="2026-09-09", end_date="2026-09-11",
        city="San Francisco", country="USA",
        est_attendees=12000, vip_count=400, speaker_count=200,
        category="conference",
        industry_tags="SaaS,software,startup,B2B,sales,marketing,product",
        audience_personas="CEO,CTO,VP sales,marketing director,founder,investor,VP engineering",
        description="The world's largest B2B SaaS conference.",
        ticket_price_usd=1599.0, price_description="From $1,599",
        registration_url="https://www.saastrannual.com/",
        source_url="https://www.saastr.com/",
    ),
    _ev(
        name="ProductCon Singapore 2026",
        start_date="2026-10-21", end_date="2026-10-21",
        city="Singapore", country="Singapore",
        est_attendees=800, vip_count=30, speaker_count=20,
        category="conference",
        industry_tags="product management,tech,SaaS,AI,startup",
        audience_personas="Head of Product,VP Product,product manager,CTO,developer",
        description="Product Management Festival — Singapore edition.",
        ticket_price_usd=500.0, price_description="From $500",
        registration_url="https://www.productschool.com/productcon/singapore/",
        source_url="https://www.productschool.com/",
    ),
    _ev(
        name="Slush Helsinki 2026",
        start_date="2026-11-18", end_date="2026-11-19",
        city="Helsinki", country="Finland",
        est_attendees=12000, vip_count=500, speaker_count=300,
        category="conference",
        industry_tags="startup,venture capital,tech,AI,deep tech",
        audience_personas="startup founder,investor,VC,CTO,CEO",
        description="Europe's leading startup conference.",
        ticket_price_usd=1200.0, price_description="From €1,200",
        registration_url="https://www.slush.org/",
        source_url="https://www.slush.org/",
    ),

    # ══════════════════════════════════════════════════════
    # HR TECH
    # ══════════════════════════════════════════════════════
    _ev(
        name="HR Tech Conference 2026",
        start_date="2026-09-22", end_date="2026-09-25",
        city="Las Vegas", country="USA",
        est_attendees=10000, vip_count=300, speaker_count=150,
        category="conference",
        industry_tags="HR tech,human resources,talent,workforce,people ops,AI",
        audience_personas="CHRO,HR director,head of people,talent acquisition,CEO",
        description="The world's largest HR technology event.",
        ticket_price_usd=2000.0, price_description="From $2,000",
        registration_url="https://www.hrtechnologyconference.com/",
        source_url="https://www.hrtechnologyconference.com/",
    ),
    _ev(
        name="People Matters TechHR India 2026",
        start_date="2026-08-06", end_date="2026-08-07",
        city="Gurugram", country="India",
        est_attendees=3000, vip_count=100, speaker_count=80,
        category="conference",
        industry_tags="HR tech,talent,workforce,people ops,India,future of work",
        audience_personas="CHRO,HR director,head of people,talent acquisition,CEO",
        description="India's largest HR technology conference.",
        ticket_price_usd=200.0, price_description="From ₹15,000",
        registration_url="https://peoplematters.in/techhr/",
        source_url="https://peoplematters.in/",
    ),

    # ══════════════════════════════════════════════════════
    # CYBERSECURITY
    # ══════════════════════════════════════════════════════
    _ev(
        name="RSA Conference 2027",
        start_date="2027-04-27", end_date="2027-04-30",
        city="San Francisco", country="USA",
        est_attendees=45000, vip_count=1500, speaker_count=400,
        category="conference",
        industry_tags="cybersecurity,infosec,tech,cloud security,AI,enterprise",
        audience_personas="CISO,security director,CTO,CIO,IT director,security architect",
        description="The world's leading cybersecurity conference and expo.",
        ticket_price_usd=2695.0, price_description="From $2,695",
        registration_url="https://www.rsaconference.com/",
        source_url="https://www.rsaconference.com/",
    ),
    _ev(
        name="GovWare 2026",
        start_date="2026-10-20", end_date="2026-10-22",
        city="Singapore", country="Singapore",
        est_attendees=3000, vip_count=120, speaker_count=60,
        category="conference",
        industry_tags="cybersecurity,government,tech,infosec,ASEAN",
        audience_personas="CISO,CIO,IT director,government official,security architect",
        description="Singapore's premier government and enterprise cybersecurity conference.",
        ticket_price_usd=1200.0, price_description="From $1,200",
        registration_url="https://www.govware.com.sg/",
        source_url="https://www.govware.com.sg/",
    ),
    _ev(
        name="Black Hat USA 2026",
        start_date="2026-08-01", end_date="2026-08-06",
        city="Las Vegas", country="USA",
        est_attendees=20000, vip_count=500, speaker_count=300,
        category="conference",
        industry_tags="cybersecurity,infosec,hacking,network security,CISO",
        audience_personas="CISO,security engineer,penetration tester,security director,CTO",
        description="The world's leading information security conference.",
        ticket_price_usd=2995.0, price_description="From $2,995",
        registration_url="https://www.blackhat.com/us-26/",
        source_url="https://www.blackhat.com/",
    ),

    # ══════════════════════════════════════════════════════
    # MANUFACTURING / INDUSTRY 4.0
    # ══════════════════════════════════════════════════════
    _ev(
        name="Smart Manufacturing Summit Asia 2026",
        start_date="2026-09-02", end_date="2026-09-03",
        city="Singapore", country="Singapore",
        est_attendees=1000, vip_count=50, speaker_count=35,
        category="summit",
        industry_tags="manufacturing,smart factory,IoT,industry 4.0,automation,robotics",
        audience_personas="COO,VP manufacturing,plant manager,digital transformation leader,CTO",
        description="Asia's dedicated smart manufacturing summit for factory leaders.",
        ticket_price_usd=1500.0, price_description="From $1,500",
        registration_url="https://www.terrapinn.com/conference/smart-manufacturing-summit/",
        source_url="https://www.terrapinn.com/",
    ),
    _ev(
        name="India Manufacturing Summit 2026",
        start_date="2026-09-17", end_date="2026-09-18",
        city="Pune", country="India",
        est_attendees=1500, vip_count=60, speaker_count=40,
        category="summit",
        industry_tags="manufacturing,India,automation,supply chain,industry 4.0",
        audience_personas="COO,VP manufacturing,plant manager,procurement head,CTO",
        description="India's largest manufacturing technology and innovation summit.",
        ticket_price_usd=200.0, price_description="From ₹15,000",
        registration_url="https://www.indiamanufacturingsummit.com/",
        source_url="https://www.indiamanufacturingsummit.com/",
    ),
    _ev(
        name="Hannover Messe 2027",
        start_date="2027-04-26", end_date="2027-04-30",
        city="Hannover", country="Germany",
        est_attendees=130000, vip_count=5000, speaker_count=500,
        category="expo",
        industry_tags="manufacturing,industrial,automation,robotics,IoT,energy,AI",
        audience_personas="COO,VP manufacturing,plant manager,CTO,procurement head",
        description="The world's leading trade fair for industrial technology.",
        ticket_price_usd=0.0, price_description="See website",
        registration_url="https://www.hannovermesse.de/",
        source_url="https://www.hannovermesse.de/",
    ),

    # ══════════════════════════════════════════════════════
    # MARKETING / MARTECH
    # ══════════════════════════════════════════════════════
    _ev(
        name="Advertising Week Asia 2026",
        start_date="2026-07-21", end_date="2026-07-23",
        city="Tokyo", country="Japan",
        est_attendees=8000, vip_count=200, speaker_count=150,
        category="conference",
        industry_tags="marketing,advertising,martech,brand,digital marketing,AI",
        audience_personas="CMO,marketing director,brand manager,creative director,media buyer",
        description="Asia's premier advertising and marketing festival.",
        ticket_price_usd=800.0, price_description="From $800",
        registration_url="https://advertisingweek.com/asia/",
        source_url="https://advertisingweek.com/",
    ),
    _ev(
        name="Marketing Festival India 2026",
        start_date="2026-07-09", end_date="2026-07-10",
        city="Mumbai", country="India",
        est_attendees=2000, vip_count=80, speaker_count=60,
        category="conference",
        industry_tags="marketing,advertising,digital marketing,martech,content,India",
        audience_personas="CMO,marketing director,brand manager,content head,VP marketing",
        description="India's leading marketing and digital advertising conference.",
        ticket_price_usd=150.0, price_description="From ₹12,000",
        registration_url="https://marketingfestival.in/",
        source_url="https://marketingfestival.in/",
    ),

    # ══════════════════════════════════════════════════════
    # DATA & ANALYTICS
    # ══════════════════════════════════════════════════════
    _ev(
        name="Gartner Data & Analytics Summit 2027",
        start_date="2027-03-08", end_date="2027-03-10",
        city="Orlando", country="USA",
        est_attendees=5000, vip_count=300, speaker_count=100,
        category="summit",
        industry_tags="data,analytics,AI,machine learning,cloud,business intelligence",
        audience_personas="CDO,head of data,CIO,data engineer,analytics leader,CTO",
        description="Gartner's flagship data and analytics summit for data leaders.",
        ticket_price_usd=3500.0, price_description="From $3,500",
        registration_url="https://www.gartner.com/en/conferences/na/data-analytics-us",
        source_url="https://www.gartner.com/",
    ),
    _ev(
        name="Big Data & AI World Singapore 2026",
        start_date="2026-10-07", end_date="2026-10-08",
        city="Singapore", country="Singapore",
        est_attendees=6000, vip_count=180, speaker_count=120,
        category="expo",
        industry_tags="data,AI,machine learning,analytics,cloud,big data,ASEAN",
        audience_personas="CDO,head of data,CIO,data engineer,analytics leader,CTO",
        description="Southeast Asia's leading big data and AI conference and exhibition.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.bigdataworld.com/singapore/",
        source_url="https://www.bigdataworld.com/",
    ),

    # ══════════════════════════════════════════════════════
    # ENERGY / SUSTAINABILITY
    # ══════════════════════════════════════════════════════
    _ev(
        name="COP31 — UN Climate Conference 2026",
        start_date="2026-11-09", end_date="2026-11-20",
        city="Istanbul", country="Turkey",
        est_attendees=40000, vip_count=5000, speaker_count=500,
        category="conference",
        industry_tags="energy,climate,sustainability,ESG,net zero,cleantech,policy",
        audience_personas="CEO,sustainability director,government official,investor,CDO",
        description="United Nations annual climate change conference — COP31.",
        ticket_price_usd=0.0, price_description="Accreditation required",
        registration_url="https://unfccc.int/cop31",
        source_url="https://unfccc.int/",
    ),
    _ev(
        name="International Greentech & Eco Products Exhibition 2026",
        start_date="2026-09-30", end_date="2026-10-02",
        city="Kuala Lumpur", country="Malaysia",
        est_attendees=10000, vip_count=200, speaker_count=80,
        category="expo",
        industry_tags="energy,cleantech,sustainability,ESG,renewable,green tech",
        audience_personas="CEO,sustainability director,COO,government official,investor",
        description="Southeast Asia's leading greentech and sustainable products exhibition.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.igem.com.my/",
        source_url="https://www.igem.com.my/",
    ),
    _ev(
        name="EnergyTech Summit India 2026",
        start_date="2026-09-03", end_date="2026-09-04",
        city="New Delhi", country="India",
        est_attendees=2000, vip_count=80, speaker_count=50,
        category="summit",
        industry_tags="energy,renewable,solar,cleantech,ESG,India",
        audience_personas="CEO,sustainability director,COO,government official,investor",
        description="India's leading energy technology and clean energy summit.",
        ticket_price_usd=150.0, price_description="From ₹12,000",
        registration_url="https://www.energytechsummit.in/",
        source_url="https://www.energytechsummit.in/",
    ),

    # ══════════════════════════════════════════════════════
    # RETAIL / ECOMMERCE
    # ══════════════════════════════════════════════════════
    _ev(
        name="NRF Retail's Big Show 2027",
        start_date="2027-01-10", end_date="2027-01-12",
        city="New York", country="USA",
        est_attendees=40000, vip_count=1000, speaker_count=200,
        category="conference",
        industry_tags="retail,ecommerce,consumer goods,omnichannel,AI,tech",
        audience_personas="CMO,CEO,CTO,head of ecommerce,merchandising director,VP retail",
        description="The world's largest retail conference and expo.",
        ticket_price_usd=2200.0, price_description="From $2,200",
        registration_url="https://nrfbigshow.nrf.com/",
        source_url="https://nrfbigshow.nrf.com/",
    ),
    _ev(
        name="Seamless Asia 2026",
        start_date="2026-08-26", end_date="2026-08-27",
        city="Singapore", country="Singapore",
        est_attendees=5000, vip_count=150, speaker_count=80,
        category="conference",
        industry_tags="ecommerce,retail,fintech,payments,digital,ASEAN,logistics",
        audience_personas="CEO,CMO,CTO,head of ecommerce,payments director,VP digital",
        description="Asia's leading e-commerce, payments and retail technology event.",
        ticket_price_usd=0.0, price_description="Free with registration",
        registration_url="https://seamless-asia.com/",
        source_url="https://seamless-asia.com/",
    ),
    _ev(
        name="India eCommerce Summit 2026",
        start_date="2026-07-15", end_date="2026-07-16",
        city="Bangalore", country="India",
        est_attendees=2000, vip_count=80, speaker_count=50,
        category="summit",
        industry_tags="ecommerce,retail,D2C,payments,logistics,India",
        audience_personas="CMO,CEO,CTO,head of ecommerce,VP digital,founder",
        description="India's premier e-commerce and D2C summit.",
        ticket_price_usd=150.0, price_description="From ₹10,000",
        registration_url="https://www.indiaecommercesummit.com/",
        source_url="https://www.indiaecommercesummit.com/",
    ),

    # ══════════════════════════════════════════════════════
    # ENTERPRISE / DIGITAL TRANSFORMATION
    # ══════════════════════════════════════════════════════
    _ev(
        name="Gartner IT Symposium/Xpo 2026 — APAC",
        start_date="2026-11-16", end_date="2026-11-19",
        city="Gold Coast", country="Australia",
        est_attendees=4000, vip_count=300, speaker_count=100,
        category="summit",
        industry_tags="digital transformation,tech,cloud,AI,enterprise,CIO",
        audience_personas="CIO,CTO,CDO,IT director,digital transformation leader,VP Engineering",
        description="Gartner's flagship event for IT and business leaders — Asia Pacific edition.",
        ticket_price_usd=4500.0, price_description="From $4,500",
        registration_url="https://www.gartner.com/en/conferences/apac/symposium-australia",
        source_url="https://www.gartner.com/",
    ),
    _ev(
        name="NASSCOM Technology & Leadership Forum 2027",
        start_date="2027-02-10", end_date="2027-02-12",
        city="Mumbai", country="India",
        est_attendees=3000, vip_count=400, speaker_count=100,
        category="conference",
        industry_tags="tech,IT,AI,digital transformation,India,SaaS,startup",
        audience_personas="CEO,CTO,CIO,VP engineering,founder,investor,digital transformation leader",
        description="India's most prestigious tech leadership forum by NASSCOM.",
        ticket_price_usd=400.0, price_description="From ₹35,000",
        registration_url="https://nasscomtechleadership.org/",
        source_url="https://nasscomtechleadership.org/",
    ),
    _ev(
        name="IDC Future Enterprise Summit India 2026",
        start_date="2026-08-13", end_date="2026-08-13",
        city="Bangalore", country="India",
        est_attendees=600, vip_count=80, speaker_count=25,
        category="summit",
        industry_tags="digital transformation,AI,cloud,tech,enterprise,India",
        audience_personas="CIO,CTO,CDO,VP IT,digital transformation leader,IT director",
        description="IDC's flagship CIO leadership summit for India's enterprise technology community.",
        ticket_price_usd=0.0, price_description="By invitation",
        registration_url="https://www.idc.com/ap/events",
        source_url="https://www.idc.com/",
    ),

    # ══════════════════════════════════════════════════════
    # SE ASIA SPECIFIC (SACEOS / MyCEB territory)
    # ══════════════════════════════════════════════════════
    _ev(
        name="GITEX Asia 2026",
        start_date="2026-06-23", end_date="2026-06-25",
        city="Singapore", country="Singapore",
        est_attendees=15000, vip_count=500, speaker_count=200,
        category="expo",
        industry_tags="tech,AI,cloud,cybersecurity,smart city,ASEAN,digital transformation",
        audience_personas="CIO,CTO,CDO,CISO,government official,startup founder,investor",
        description="GITEX Asia — the region's largest technology event.",
        ticket_price_usd=0.0, price_description="Free with registration",
        registration_url="https://www.gitex.com/gitex-asia/",
        source_url="https://www.gitex.com/",
    ),
    _ev(
        name="MIDE Malaysia International Defence Exhibition 2026",
        start_date="2026-09-14", end_date="2026-09-17",
        city="Kuala Lumpur", country="Malaysia",
        est_attendees=30000, vip_count=500, speaker_count=100,
        category="expo",
        industry_tags="defence,security,aerospace,manufacturing,government,Malaysia",
        audience_personas="government official,COO,VP operations,procurement head",
        description="Malaysia's premier international defence and security exhibition.",
        ticket_price_usd=0.0, price_description="See website",
        registration_url="https://www.mide.com.my/",
        source_url="https://www.mide.com.my/",
    ),
    _ev(
        name="BioAsia 2026",
        start_date="2026-09-21", end_date="2026-09-23",
        city="Singapore", country="Singapore",
        est_attendees=5000, vip_count=200, speaker_count=100,
        category="conference",
        industry_tags="biotech,pharma,healthcare,life sciences,AI,ASEAN",
        audience_personas="CEO,CTO,R&D director,investor,hospital administrator,CDO",
        description="Asia's leading biotech and life sciences conference.",
        ticket_price_usd=800.0, price_description="From $800",
        registration_url="https://www.bioasia.com.sg/",
        source_url="https://www.bioasia.com.sg/",
    ),

    # ══════════════════════════════════════════════════════
    # NEAR-TERM (next 3 months from May 2026)
    # ══════════════════════════════════════════════════════
    _ev(
        name="Gartner Security & Risk Management Summit 2026",
        start_date="2026-06-08", end_date="2026-06-10",
        city="National Harbor", country="USA",
        est_attendees=4000, vip_count=200, speaker_count=100,
        category="summit",
        industry_tags="cybersecurity,risk management,infosec,enterprise,AI",
        audience_personas="CISO,CIO,security director,IT director,risk manager",
        description="Gartner's annual security leadership summit.",
        ticket_price_usd=3200.0, price_description="From $3,200",
        registration_url="https://www.gartner.com/en/conferences/na/security-us",
        source_url="https://www.gartner.com/",
    ),
    _ev(
        name="Collision Conference 2026",
        start_date="2026-06-22", end_date="2026-06-25",
        city="Toronto", country="Canada",
        est_attendees=35000, vip_count=1000, speaker_count=400,
        category="conference",
        industry_tags="tech,startup,AI,SaaS,venture capital,digital,product",
        audience_personas="CEO,CTO,startup founder,investor,VP engineering,CMO",
        description="North America's fastest-growing tech conference.",
        ticket_price_usd=1200.0, price_description="From $1,200",
        registration_url="https://collisionconf.com/",
        source_url="https://collisionconf.com/",
    ),
    _ev(
        name="VivaTech 2026",
        start_date="2026-06-10", end_date="2026-06-13",
        city="Paris", country="France",
        est_attendees=90000, vip_count=3000, speaker_count=400,
        category="expo",
        industry_tags="tech,startup,AI,innovation,digital transformation,corporate innovation",
        audience_personas="CEO,CTO,CDO,startup founder,investor,CMO,VP innovation",
        description="Europe's biggest startup and tech event.",
        ticket_price_usd=0.0, price_description="From €30",
        registration_url="https://vivatechnology.com/",
        source_url="https://vivatechnology.com/",
    ),
    _ev(
        name="London Tech Week 2026",
        start_date="2026-06-15", end_date="2026-06-19",
        city="London", country="UK",
        est_attendees=50000, vip_count=2000, speaker_count=500,
        category="conference",
        industry_tags="tech,AI,fintech,startup,digital transformation,SaaS",
        audience_personas="CEO,CTO,CDO,startup founder,investor,CMO,VP engineering",
        description="The UK's leading technology and innovation festival.",
        ticket_price_usd=0.0, price_description="Most events free",
        registration_url="https://londontechweek.com/",
        source_url="https://londontechweek.com/",
    ),
    _ev(
        name="Salesforce Connections 2026",
        start_date="2026-06-03", end_date="2026-06-04",
        city="Chicago", country="USA",
        est_attendees=15000, vip_count=400, speaker_count=150,
        category="conference",
        industry_tags="CRM,Salesforce,marketing,sales,AI,SaaS,digital commerce",
        audience_personas="CMO,VP sales,CRO,marketing director,VP digital,sales operations",
        description="Salesforce's annual marketing, commerce and service conference.",
        ticket_price_usd=0.0, price_description="Registration required",
        registration_url="https://www.salesforce.com/connections/",
        source_url="https://www.salesforce.com/",
    ),
]


class SeedConnector(BaseConnector):
    name = "Seed"

    async def fetch(self) -> List[EventCreate]:
        logger.info(f"Seed: loading {len(SEED_EVENTS)} curated events.")
        return SEED_EVENTS
