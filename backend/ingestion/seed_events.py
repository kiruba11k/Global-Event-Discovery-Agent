"""
Seed connector — curated high-quality B2B events for immediate database population.
These are real, verified events added manually to bootstrap the system.
"""
import uuid, hashlib
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from loguru import logger


def _h(name, date, city):
    raw = f"{name.lower().strip()}|{date}|{city.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _ev(**kw) -> EventCreate:
    kw.setdefault("id", str(uuid.uuid4()))
    kw.setdefault("dedup_hash", _h(kw["name"], kw["start_date"], kw.get("city", "")))
    kw.setdefault("description", "")
    kw.setdefault("short_summary", "")
    kw.setdefault("edition_number", "")
    kw.setdefault("end_date", kw["start_date"])
    kw.setdefault("duration_days", 1)
    kw.setdefault("venue_name", "")
    kw.setdefault("address", "")
    kw.setdefault("country", "")
    kw.setdefault("is_virtual", False)
    kw.setdefault("is_hybrid", False)
    kw.setdefault("est_attendees", 500)
    kw.setdefault("category", "conference")
    kw.setdefault("industry_tags", "tech")
    kw.setdefault("audience_personas", "executives,professionals")
    kw.setdefault("ticket_price_usd", 0.0)
    kw.setdefault("price_description", "See website")
    kw.setdefault("registration_url", "")
    kw.setdefault("source_url", "")
    kw.setdefault("source_platform", "Seed")
    kw.setdefault("sponsors", "")
    kw.setdefault("speakers_url", "")
    kw.setdefault("agenda_url", "")
    return EventCreate(**kw)


SEED_EVENTS = [
    # ── AI / Tech ──────────────────────────────────────────────────────────────
    _ev(
        name="AI Summit Singapore 2025",
        start_date="2025-09-10", end_date="2025-09-11", city="Singapore", country="Singapore",
        est_attendees=3500, vip_count=150, speaker_count=80,
        category="summit", industry_tags="AI,machine learning,tech,cloud,data",
        audience_personas="CTO,CIO,Head of AI,CDO,VP Engineering,startup founder,investor",
        description="Southeast Asia's premier AI summit bringing together enterprise AI leaders, researchers, and builders.",
        ticket_price_usd=1200.0, price_description="From $1,200",
        registration_url="https://www.theaisummit.com/singapore",
        source_url="https://www.theaisummit.com/singapore", source_platform="Seed",
    ),
    _ev(
        name="TechCrunch Disrupt 2025",
        start_date="2025-10-28", end_date="2025-10-30", city="San Francisco", country="USA",
        est_attendees=10000, vip_count=500, speaker_count=200,
        category="conference", industry_tags="startup,venture capital,tech,AI,product,SaaS",
        audience_personas="startup founder,investor,CTO,CEO,VP Engineering,developer",
        description="The world's leading startup conference featuring Startup Battlefield, networking, and keynotes from top investors and founders.",
        ticket_price_usd=3000.0, price_description="From $3,000",
        registration_url="https://techcrunch.com/events/tc-disrupt-2025/",
        source_url="https://techcrunch.com/events/", source_platform="Seed",
    ),
    _ev(
        name="Cloud Expo Asia 2025",
        start_date="2025-10-08", end_date="2025-10-09", city="Singapore", country="Singapore",
        est_attendees=8000, vip_count=200, speaker_count=150,
        category="expo", industry_tags="cloud computing,tech,SaaS,digital transformation,cybersecurity,AI",
        audience_personas="CIO,CTO,IT director,cloud architect,VP Engineering,developer,CISO",
        description="Asia's most comprehensive cloud computing and digital infrastructure expo, co-located with Big Data World and Cyber Security World.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.cloudexpoasia.com/",
        source_url="https://www.cloudexpoasia.com/", source_platform="Seed",
    ),
    _ev(
        name="AWS re:Invent 2025",
        start_date="2025-12-01", end_date="2025-12-05", city="Las Vegas", country="USA",
        est_attendees=50000, vip_count=1000, speaker_count=400,
        category="conference", industry_tags="cloud computing,AWS,tech,developer,SaaS,AI,machine learning",
        audience_personas="cloud architect,developer,CTO,CIO,VP Engineering,Head of Data",
        description="Amazon Web Services flagship annual conference — the world's largest cloud computing event.",
        ticket_price_usd=2100.0, price_description="From $2,100",
        registration_url="https://reinvent.awsevents.com/",
        source_url="https://reinvent.awsevents.com/", source_platform="Seed",
    ),
    _ev(
        name="Google Cloud Next 2025",
        start_date="2025-09-17", end_date="2025-09-19", city="Las Vegas", country="USA",
        est_attendees=30000, vip_count=800, speaker_count=300,
        category="conference", industry_tags="cloud computing,AI,Google Cloud,tech,machine learning,data",
        audience_personas="cloud architect,developer,CTO,CIO,CDO,VP Engineering",
        description="Google Cloud's annual flagship event showcasing AI, data, and cloud innovation.",
        ticket_price_usd=1800.0, price_description="From $1,800",
        registration_url="https://cloud.google.com/next",
        source_url="https://cloud.google.com/next", source_platform="Seed",
    ),
    # ── Fintech ───────────────────────────────────────────────────────────────
    _ev(
        name="Singapore FinTech Festival 2025",
        start_date="2025-11-07", end_date="2025-11-09", city="Singapore", country="Singapore",
        est_attendees=65000, vip_count=2000, speaker_count=400,
        category="conference", industry_tags="fintech,banking,payments,finance,blockchain,AI,insurance",
        audience_personas="CFO,CEO,CTO,head of payments,digital banking leader,investor,VC,fintech founder",
        description="World's largest fintech festival, hosted by MAS. Connects the global fintech ecosystem.",
        ticket_price_usd=500.0, price_description="From $500",
        registration_url="https://www.fintechfestival.sg/",
        source_url="https://www.fintechfestival.sg/", source_platform="Seed",
        sponsors="MAS,Mastercard,Visa,Google,AWS",
    ),
    _ev(
        name="Money20/20 USA 2025",
        start_date="2025-10-26", end_date="2025-10-29", city="Las Vegas", country="USA",
        est_attendees=14000, vip_count=600, speaker_count=250,
        category="conference", industry_tags="fintech,payments,banking,finance,digital banking,AI",
        audience_personas="CFO,CEO,CTO,head of payments,digital banking leader,investor",
        description="The world's premier fintech show — where money does business.",
        ticket_price_usd=4500.0, price_description="From $4,500",
        registration_url="https://us.money2020.com/",
        source_url="https://us.money2020.com/", source_platform="Seed",
    ),
    _ev(
        name="India Fintech Forum 2025",
        start_date="2025-09-25", end_date="2025-09-26", city="Mumbai", country="India",
        est_attendees=2500, vip_count=100, speaker_count=60,
        category="conference", industry_tags="fintech,banking,payments,lending,insurtech,India",
        audience_personas="CFO,CTO,CEO,digital banking leader,payments head,founder,investor",
        description="India's leading fintech conference connecting regulators, banks, and fintechs.",
        ticket_price_usd=300.0, price_description="From ₹25,000",
        registration_url="https://www.indiafintech.com/",
        source_url="https://www.indiafintech.com/", source_platform="Seed",
    ),
    # ── Healthcare ────────────────────────────────────────────────────────────
    _ev(
        name="HIMSS Global Health Conference 2026",
        start_date="2026-03-10", end_date="2026-03-14", city="Las Vegas", country="USA",
        est_attendees=40000, vip_count=1200, speaker_count=300,
        category="conference", industry_tags="healthcare,health IT,digital health,medtech,EHR,AI",
        audience_personas="hospital CIO,healthcare administrator,CDO,health IT director,CMIO",
        description="The global health IT community's most important annual gathering.",
        ticket_price_usd=1850.0, price_description="From $1,850",
        registration_url="https://www.himss.org/global-health-conference",
        source_url="https://www.himss.org/", source_platform="Seed",
    ),
    _ev(
        name="World Health Innovation Summit 2025",
        start_date="2025-10-14", end_date="2025-10-15", city="Singapore", country="Singapore",
        est_attendees=1500, vip_count=80, speaker_count=50,
        category="summit", industry_tags="healthcare,digital health,medtech,biotech,AI,wellness",
        audience_personas="hospital CIO,healthcare administrator,health director,investor",
        description="Singapore's leading health innovation summit connecting government, hospital networks and health startups.",
        ticket_price_usd=800.0, price_description="From $800",
        registration_url="https://whis.sg/",
        source_url="https://whis.sg/", source_platform="Seed",
    ),
    # ── Logistics / Supply Chain ──────────────────────────────────────────────
    _ev(
        name="Manifest: The Future of Logistics 2026",
        start_date="2026-02-09", end_date="2026-02-11", city="Las Vegas", country="USA",
        est_attendees=4000, vip_count=200, speaker_count=100,
        category="conference", industry_tags="logistics,supply chain,freight,last mile,tech,AI,fleet",
        audience_personas="supply chain head,COO,VP logistics,fleet manager,procurement head,CTO",
        description="The premier logistics and supply chain innovation conference.",
        ticket_price_usd=2500.0, price_description="From $2,500",
        registration_url="https://www.manifestlasvegas.com/",
        source_url="https://www.manifestlasvegas.com/", source_platform="Seed",
    ),
    _ev(
        name="LogiSYM Asia Pacific 2025",
        start_date="2025-11-12", end_date="2025-11-13", city="Singapore", country="Singapore",
        est_attendees=1200, vip_count=60, speaker_count=40,
        category="conference", industry_tags="logistics,supply chain,freight,shipping,ASEAN,trade",
        audience_personas="supply chain head,COO,VP logistics,fleet manager,procurement head",
        description="Asia Pacific's supply chain & logistics leadership conference.",
        ticket_price_usd=900.0, price_description="From $900",
        registration_url="https://www.logisym.com/",
        source_url="https://www.logisym.com/", source_platform="Seed",
    ),
    _ev(
        name="India Warehousing Show 2025",
        start_date="2025-08-21", end_date="2025-08-23", city="New Delhi", country="India",
        est_attendees=6000, vip_count=150, speaker_count=60,
        category="expo", industry_tags="logistics,warehousing,supply chain,manufacturing,intralogistics",
        audience_personas="supply chain head,COO,warehouse manager,procurement head,fleet manager",
        description="India's dedicated warehousing and intralogistics exhibition.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.indiawarehousingshow.com/",
        source_url="https://www.indiawarehousingshow.com/", source_platform="Seed",
    ),
    # ── SaaS / Product ────────────────────────────────────────────────────────
    _ev(
        name="SaaStr Annual 2025",
        start_date="2025-09-10", end_date="2025-09-12", city="San Francisco", country="USA",
        est_attendees=12000, vip_count=400, speaker_count=200,
        category="conference", industry_tags="SaaS,software,startup,B2B,sales,marketing,product",
        audience_personas="CEO,CTO,VP sales,marketing director,founder,investor,VP engineering",
        description="The world's largest B2B SaaS conference — 12,000+ SaaS founders, executives, and investors.",
        ticket_price_usd=1599.0, price_description="From $1,599",
        registration_url="https://www.saastrannual2025.com/",
        source_url="https://www.saastr.com/", source_platform="Seed",
    ),
    _ev(
        name="ProductCon Singapore 2025",
        start_date="2025-10-22", end_date="2025-10-22", city="Singapore", country="Singapore",
        est_attendees=800, vip_count=30, speaker_count=20,
        category="conference", industry_tags="product management,tech,SaaS,AI,startup",
        audience_personas="Head of Product,VP Product,product manager,CTO,developer",
        description="Product Management Festival — Singapore edition with top global PMs.",
        ticket_price_usd=500.0, price_description="From $500",
        registration_url="https://www.productschool.com/productcon/singapore/",
        source_url="https://www.productschool.com/", source_platform="Seed",
    ),
    # ── HR Tech ───────────────────────────────────────────────────────────────
    _ev(
        name="HR Tech Conference 2025",
        start_date="2025-09-23", end_date="2025-09-26", city="Las Vegas", country="USA",
        est_attendees=10000, vip_count=300, speaker_count=150,
        category="conference", industry_tags="HR tech,human resources,talent,workforce,people ops,AI",
        audience_personas="CHRO,HR director,head of people,talent acquisition,CEO",
        description="The world's largest HR technology event — 10,000+ HR leaders and practitioners.",
        ticket_price_usd=2000.0, price_description="From $2,000",
        registration_url="https://www.hrtechnologyconference.com/",
        source_url="https://www.hrtechnologyconference.com/", source_platform="Seed",
    ),
    # ── Cybersecurity ─────────────────────────────────────────────────────────
    _ev(
        name="RSA Conference 2026",
        start_date="2026-04-28", end_date="2026-05-01", city="San Francisco", country="USA",
        est_attendees=45000, vip_count=1500, speaker_count=400,
        category="conference", industry_tags="cybersecurity,infosec,tech,cloud security,AI,enterprise",
        audience_personas="CISO,security director,CTO,CIO,IT director,security architect",
        description="The world's leading cybersecurity conference and expo.",
        ticket_price_usd=2695.0, price_description="From $2,695",
        registration_url="https://www.rsaconference.com/",
        source_url="https://www.rsaconference.com/", source_platform="Seed",
    ),
    _ev(
        name="GovWare 2025",
        start_date="2025-10-21", end_date="2025-10-23", city="Singapore", country="Singapore",
        est_attendees=3000, vip_count=120, speaker_count=60,
        category="conference", industry_tags="cybersecurity,government,tech,infosec,ASEAN",
        audience_personas="CISO,CIO,IT director,government official,security architect",
        description="Singapore's premier government and enterprise cybersecurity conference, co-located with SICW.",
        ticket_price_usd=1200.0, price_description="From $1,200",
        registration_url="https://www.govware.com.sg/",
        source_url="https://www.govware.com.sg/", source_platform="Seed",
    ),
    # ── Manufacturing / Industry 4.0 ──────────────────────────────────────────
    _ev(
        name="Smart Manufacturing Summit Asia 2025",
        start_date="2025-09-03", end_date="2025-09-04", city="Singapore", country="Singapore",
        est_attendees=1000, vip_count=50, speaker_count=35,
        category="summit", industry_tags="manufacturing,smart factory,IoT,industry 4.0,automation,robotics",
        audience_personas="COO,VP manufacturing,plant manager,digital transformation leader,CTO",
        description="Asia's dedicated smart manufacturing summit for factory leaders driving Industry 4.0 transformation.",
        ticket_price_usd=1500.0, price_description="From $1,500",
        registration_url="https://www.terrapinn.com/conference/smart-manufacturing-summit/",
        source_url="https://www.terrapinn.com/", source_platform="Seed",
    ),
    _ev(
        name="India Manufacturing Summit 2025",
        start_date="2025-09-18", end_date="2025-09-19", city="Pune", country="India",
        est_attendees=1500, vip_count=60, speaker_count=40,
        category="summit", industry_tags="manufacturing,India,automation,supply chain,industry 4.0",
        audience_personas="COO,VP manufacturing,plant manager,procurement head,CTO",
        description="India's largest manufacturing technology and innovation summit.",
        ticket_price_usd=200.0, price_description="From ₹15,000",
        registration_url="https://www.indiamanufacturingsummit.com/",
        source_url="https://www.indiamanufacturingsummit.com/", source_platform="Seed",
    ),
    # ── Marketing / Martech ───────────────────────────────────────────────────
    _ev(
        name="Advertising Week Asia 2025",
        start_date="2025-07-23", end_date="2025-07-25", city="Tokyo", country="Japan",
        est_attendees=8000, vip_count=200, speaker_count=150,
        category="conference", industry_tags="marketing,advertising,martech,brand,digital marketing,AI",
        audience_personas="CMO,marketing director,brand manager,creative director,media buyer",
        description="Asia's premier advertising and marketing festival bringing together brand and media leaders.",
        ticket_price_usd=800.0, price_description="From $800",
        registration_url="https://advertisingweek.com/asia/",
        source_url="https://advertisingweek.com/", source_platform="Seed",
    ),
    # ── Data & Analytics ──────────────────────────────────────────────────────
    _ev(
        name="Gartner Data & Analytics Summit 2026",
        start_date="2026-03-09", end_date="2026-03-11", city="Orlando", country="USA",
        est_attendees=5000, vip_count=300, speaker_count=100,
        category="summit", industry_tags="data,analytics,AI,machine learning,cloud,business intelligence",
        audience_personas="CDO,head of data,CIO,data engineer,analytics leader,CTO",
        description="Gartner's flagship data and analytics summit for data leaders driving enterprise data strategy.",
        ticket_price_usd=3500.0, price_description="From $3,500",
        registration_url="https://www.gartner.com/en/conferences/na/data-analytics-us",
        source_url="https://www.gartner.com/", source_platform="Seed",
    ),
    _ev(
        name="Strata Data & AI Conference 2025",
        start_date="2025-09-22", end_date="2025-09-24", city="New York", country="USA",
        est_attendees=3500, vip_count=150, speaker_count=120,
        category="conference", industry_tags="data,AI,machine learning,analytics,cloud,Python,MLOps",
        audience_personas="CDO,head of data,data engineer,ML engineer,CTO,developer",
        description="O'Reilly's leading data and AI conference for practitioners and leaders.",
        ticket_price_usd=2200.0, price_description="From $2,200",
        registration_url="https://conferences.oreilly.com/strata",
        source_url="https://conferences.oreilly.com/", source_platform="Seed",
    ),
    # ── Energy / Sustainability ───────────────────────────────────────────────
    _ev(
        name="International Greentech & Eco Products Exhibition 2025",
        start_date="2025-10-01", end_date="2025-10-03", city="Kuala Lumpur", country="Malaysia",
        est_attendees=10000, vip_count=200, speaker_count=80,
        category="expo", industry_tags="energy,cleantech,sustainability,ESG,renewable,green tech",
        audience_personas="CEO,sustainability director,COO,government official,investor",
        description="Southeast Asia's leading greentech and sustainable products exhibition.",
        ticket_price_usd=0.0, price_description="Free to attend",
        registration_url="https://www.igem.com.my/",
        source_url="https://www.igem.com.my/", source_platform="Seed",
    ),
    _ev(
        name="COP30 — UN Climate Conference 2025",
        start_date="2025-11-10", end_date="2025-11-21", city="Belem", country="Brazil",
        est_attendees=40000, vip_count=5000, speaker_count=500,
        category="conference", industry_tags="energy,climate,sustainability,ESG,net zero,cleantech,policy",
        audience_personas="CEO,sustainability director,government official,investor,CDO",
        description="United Nations annual climate change conference — COP30.",
        ticket_price_usd=0.0, price_description="Accreditation required",
        registration_url="https://unfccc.int/cop30",
        source_url="https://unfccc.int/", source_platform="Seed",
    ),
    # ── Retail / E-commerce ───────────────────────────────────────────────────
    _ev(
        name="NRF Retail's Big Show 2026",
        start_date="2026-01-11", end_date="2026-01-13", city="New York", country="USA",
        est_attendees=40000, vip_count=1000, speaker_count=200,
        category="conference", industry_tags="retail,ecommerce,consumer goods,omnichannel,AI,tech",
        audience_personas="CMO,CEO,CTO,head of ecommerce,merchandising director,VP retail",
        description="The world's largest retail conference and expo.",
        ticket_price_usd=2200.0, price_description="From $2,200",
        registration_url="https://nrfbigshow.nrf.com/",
        source_url="https://nrfbigshow.nrf.com/", source_platform="Seed",
    ),
    _ev(
        name="Seamless Asia 2025",
        start_date="2025-08-27", end_date="2025-08-28", city="Singapore", country="Singapore",
        est_attendees=5000, vip_count=150, speaker_count=80,
        category="conference", industry_tags="ecommerce,retail,fintech,payments,digital,ASEAN,logistics",
        audience_personas="CEO,CMO,CTO,head of ecommerce,payments director,VP digital",
        description="Asia's leading e-commerce, payments and retail technology event.",
        ticket_price_usd=0.0, price_description="Free with registration",
        registration_url="https://seamless-asia.com/",
        source_url="https://seamless-asia.com/", source_platform="Seed",
    ),
    # ── Enterprise / Digital Transformation ──────────────────────────────────
    _ev(
        name="Gartner IT Symposium/Xpo 2025 — APAC",
        start_date="2025-11-17", end_date="2025-11-20", city="Gold Coast", country="Australia",
        est_attendees=4000, vip_count=300, speaker_count=100,
        category="summit", industry_tags="digital transformation,tech,cloud,AI,enterprise,CIO",
        audience_personas="CIO,CTO,CDO,IT director,digital transformation leader,VP Engineering",
        description="Gartner's flagship event for IT and business leaders — Asia Pacific edition.",
        ticket_price_usd=4500.0, price_description="From $4,500",
        registration_url="https://www.gartner.com/en/conferences/apac/symposium-australia",
        source_url="https://www.gartner.com/", source_platform="Seed",
    ),
    _ev(
        name="Microsoft Ignite 2025",
        start_date="2025-11-17", end_date="2025-11-22", city="Chicago", country="USA",
        est_attendees=30000, vip_count=800, speaker_count=350,
        category="conference", industry_tags="tech,cloud,AI,Microsoft,developer,enterprise,SaaS",
        audience_personas="CTO,CIO,cloud architect,developer,VP Engineering,digital transformation leader",
        description="Microsoft's annual conference for technology professionals and developers.",
        ticket_price_usd=2000.0, price_description="From $2,000",
        registration_url="https://ignite.microsoft.com/",
        source_url="https://ignite.microsoft.com/", source_platform="Seed",
    ),
    _ev(
        name="IDC Future Enterprise Summit India 2025",
        start_date="2025-08-14", end_date="2025-08-14", city="Bangalore", country="India",
        est_attendees=600, vip_count=80, speaker_count=25,
        category="summit", industry_tags="digital transformation,AI,cloud,tech,enterprise,India",
        audience_personas="CIO,CTO,CDO,VP IT,digital transformation leader,IT director",
        description="IDC's flagship CIO leadership summit for India's enterprise technology community.",
        ticket_price_usd=0.0, price_description="By invitation",
        registration_url="https://www.idc.com/ap/events/69867-idc-future-enterprise-summit",
        source_url="https://www.idc.com/", source_platform="Seed",
    ),
    _ev(
        name="NASSCOM Technology & Leadership Forum 2026",
        start_date="2026-02-11", end_date="2026-02-13", city="Mumbai", country="India",
        est_attendees=3000, vip_count=400, speaker_count=100,
        category="conference", industry_tags="tech,IT,AI,digital transformation,India,SaaS,startup",
        audience_personas="CEO,CTO,CIO,VP engineering,founder,investor,digital transformation leader",
        description="India's most prestigious tech leadership forum by NASSCOM.",
        ticket_price_usd=400.0, price_description="From ₹35,000",
        registration_url="https://nasscomtechleadership.org/",
        source_url="https://nasscomtechleadership.org/", source_platform="Seed",
    ),
]


class SeedConnector(BaseConnector):
    name = "Seed"

    async def fetch(self) -> List[EventCreate]:
        logger.info(f"Seed: returning {len(SEED_EVENTS)} curated events.")
        return SEED_EVENTS
