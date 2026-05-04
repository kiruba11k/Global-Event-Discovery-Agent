"""Industry tagger — keyword-based classification."""
from typing import Tuple

INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "tech": ["technology","software","cloud","AI","artificial intelligence","machine learning","data","digital","SaaS","platform","developer","devops","kubernetes","API","cybersecurity","infosec","open source"],
    "finance": ["fintech","banking","finance","financial","payments","lending","insurance","wealth","treasury","trade finance","capital markets","cryptocurrency","blockchain","DeFi","regtech"],
    "healthcare": ["health","healthcare","medtech","medical","pharma","biotech","clinical","hospital","telemedicine","digital health","wellness","patient","EMR","EHR"],
    "logistics": ["logistics","supply chain","fleet","transport","shipping","warehousing","intralogistics","freight","last mile","fulfilment","customs","trade","procurement"],
    "retail": ["retail","ecommerce","e-commerce","consumer goods","fashion","FMCG","D2C","omnichannel","merchandising","POS"],
    "energy": ["energy","oil","gas","renewable","solar","wind","cleantech","sustainability","ESG","net zero","climate"],
    "manufacturing": ["manufacturing","industrial","factory","automation","robotics","IoT","industry 4.0","smart factory","CNC","3D printing"],
    "hr": ["human resources","HR","talent","workforce","people ops","employee experience","recruitment","future of work"],
    "marketing": ["marketing","advertising","content","SEO","social media","growth","brand","martech","demand generation"],
    "legal": ["legal","law","compliance","regulatory","governance","legaltech"],
}

PERSONA_KEYWORDS: dict[str, list[str]] = {
    "CIO": ["CIO","chief information officer","IT leader","head of IT"],
    "CTO": ["CTO","chief technology officer","tech leader","head of tech","VP engineering"],
    "CDO": ["CDO","chief data officer","head of data","data leader"],
    "CISO": ["CISO","chief information security","head of security","security leader"],
    "CEO": ["CEO","chief executive","managing director","founder"],
    "CFO": ["CFO","chief financial officer","finance director","treasurer"],
    "COO": ["COO","operations director","head of operations","VP operations"],
    "developer": ["developer","engineer","architect","programmer","devops"],
    "investor": ["investor","VC","venture capital","fund manager"],
    "founder": ["founder","entrepreneur","startup","co-founder"],
    "marketing leader": ["CMO","marketing director","head of marketing","demand gen"],
    "sales leader": ["VP sales","head of sales","chief revenue","CRO","sales director"],
    "HR leader": ["CHRO","HR director","head of people","talent acquisition"],
    "supply chain leader": ["supply chain","procurement","logistics director","fleet manager"],
}


def tag_industries(text: str) -> str:
    text_lower = text.lower()
    matched = [ind for ind, kws in INDUSTRY_KEYWORDS.items() if any(kw.lower() in text_lower for kw in kws)]
    return ",".join(matched) if matched else "general"


def tag_personas(text: str) -> str:
    text_lower = text.lower()
    matched = [p for p, kws in PERSONA_KEYWORDS.items() if any(kw.lower() in text_lower for kw in kws)]
    return ",".join(matched) if matched else "business professional"


def enrich_event_tags(name: str, description: str, existing_tags: str) -> Tuple[str, str]:
    combined_text = f"{name} {description}"
    new_industries = tag_industries(combined_text)
    new_personas = tag_personas(combined_text)
    existing_set = set(t.strip() for t in existing_tags.split(",") if t.strip())
    new_set = set(t.strip() for t in new_industries.split(",") if t.strip())
    merged = ",".join(sorted(existing_set | new_set))
    return merged, new_personas
