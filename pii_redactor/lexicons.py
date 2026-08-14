from __future__ import annotations

HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "shri", "smt", "sri", "sh",
    "capt", "col", "maj", "gen", "justice", "hon", "adv", "ca", "cs", "cma",
}

NAME_PARTICLES = {"de", "da", "van", "von", "der", "den", "bin", "ibn", "al", "el", "la", "le"}

NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

STRONG_ORG_SUFFIXES = [
    "Private Limited", "Public Limited Company", "Limited Liability Partnership",
    "Pvt. Ltd.", "Pvt Ltd", "Limited", "Ltd.", "Ltd",
    "LLP", "LLC", "L.L.C.", "PLC",
    "Incorporated", "Inc.", "Inc", "Corporation", "Corp.", "Corp",
    "GmbH", "S.A.", "N.V.", "B.V.", "A/S", "AB",
    "Family Trust", "Foundation",
]

WEAK_ORG_SUFFIXES = [
    "& Sons", "and Sons", "& Co.", "Associates", "Enterprises",
    "Industries", "Holdings", "Ventures", "Partners", "Bank", "Trust",
]

ORG_SUFFIXES = STRONG_ORG_SUFFIXES + WEAK_ORG_SUFFIXES

OFFER_MACHINERY_WORDS = {
    "escrow", "refund", "sponsor", "syndicate", "public", "offer", "account",
    "collection", "short", "long", "term", "cash", "designated", "working",
    "first", "sole", "anchor", "retail", "institutional", "banker", "bankers",
    "monitoring", "practicing", "practising", "statutory", "peer", "reviewed",
    "general", "special", "material", "related", "gaap", "ifrs",
    "consolidated", "standalone", "restated", "proposed", "existing",
}

GENERIC_ORG_CORE_BLOCKLIST = {
    "india", "indian", "state", "national", "central", "federal", "union",
    "global", "general", "capital", "company", "group", "bank", "trust",
    "power", "energy", "solar", "metal", "care", "link", "first", "prime",
}

ORG_INTERNAL_TOKENS = {"and", "of", "the", "for", "de", "&", "at", "in", "on"}

DEFINED_TERM_STOPWORDS = {
    "equity shares", "equity share", "red herring", "red herring prospectus",
    "draft red herring prospectus", "offer price", "offer document",
    "anchor investor", "anchor investors", "anchor investor portion",
    "promoter selling", "promoter selling shareholder",
    "promoter selling shareholders", "promoter group", "our promoters",
    "our company", "the company", "the offer", "the equity", "offer period",
    "offer closing", "offer opening", "offer procedure", "offer structure",
    "offered shares", "offer equity", "fresh issue", "bonus issue",
    "price band", "floor price", "cap price", "allocation price",
    "bid amount", "bid price", "blocked amount", "application form",
    "application supported", "book building", "book built offer",
    "book running", "lead managers", "book running lead managers",
    "working day", "working days", "designated date",
    "designated intermediaries", "designated intermediary",
    "designated stock", "designated stock exchange", "stock exchanges",
    "stock exchange", "institutional portion", "institutional investors",
    "qualified institutional", "qualified institutional buyers",
    "retail portion", "retail individual", "retail individual investors",
    "non-institutional", "mutual funds", "mutual fund portion",
    "pension funds", "life insurance", "insurance companies",
    "syndicate members", "syndicate banks", "sponsor banks",
    "registered brokers", "self certified", "self certified syndicate banks",
    "escrow account", "public offer", "public offer account",
    "net proceeds", "gross proceeds", "general corporate purposes",
    "capital structure", "risk factors", "material contracts",
    "material developments", "outstanding litigation", "industry overview",
    "restated financial", "restated financial statements",
    "summary financial statements", "statutory auditors",
    "chartered accountants", "key managerial", "key managerial personnel",
    "senior management", "senior management personnel",
    "board of directors", "our management", "our business",
    "executive director", "executive directors", "independent director",
    "independent directors", "managing director", "whole time director",
    "compliance officer", "company secretary", "contact person",
    "registered office", "corporate office", "registrar to the offer",
    "registration number", "corporate identity number",
    "proposed capital", "term description", "particulars three",
    "all bidders", "first bidder", "sole bidder", "the floor",
    "short term", "long term", "bank facilities", "power sector",
    "winding wire", "winding wires", "magnet winding wires",
    "supa facility", "the supa facility",
    "companies act", "securities contracts", "exchange board",
    "securities and exchange board of india", "reserve bank of india",
    "registrar of companies", "government of india", "central government",
    "state government", "income tax act", "master circular",
    "the depositories act", "foreign exchange management act",
    "ind as", "indian gaap", "us gaap", "ifrs",
    "united states", "republic of india", "european union", "indian rupees",
    "indian standard time",
}

PUBLIC_BODY_ALLOWLIST = {
    "national payments corporation",
    "reserve bank", "reserve bank of india",
    "export-import bank", "export-import bank of india",
    "state bank", "state bank of india",
    "bse limited",
    "national stock exchange of india limited",
    "national securities depository limited",
    "central depository services (india) limited",
    "securities and exchange board of india",
    "reserve bank of india",
    "registrar of companies",
    "the institute of chartered accountants of india",
    "insurance regulatory and development authority of india",
    "pension fund regulatory and development authority",
    "ministry of corporate affairs",
    "national payments corporation of india",
    "clearing corporation of india limited",
    "indian clearing corporation limited",
    "nse clearing limited",
}

PERSON_TOKEN_BLOCKLIST = {
    "limited", "ltd", "private", "pvt", "llp", "inc", "corporation", "corp",
    "company", "trust", "bank", "securities", "capital", "finance",
    "financial", "industries", "enterprises", "holdings", "ventures",
    "solutions", "services", "technologies", "systems", "group", "india",
    "indian", "act", "regulations", "regulation", "rules", "circular",
    "exchange", "board", "committee", "director", "directors", "officer",
    "shares", "share", "equity", "offer", "bid", "price", "portion",
    "investor", "investors", "shareholder", "shareholders", "promoter",
    "promoters", "prospectus", "herring", "fiscal", "quarter", "million",
    "billion", "crore", "lakh", "rupees", "dollars", "street", "road",
    "lane", "nagar", "society", "apartment", "floor", "tower", "wing",
    "block", "village", "taluka", "district", "state", "pune", "mumbai",
    "maharashtra", "delhi", "chennai", "kolkata", "bengaluru", "bangalore",
    "gujarat", "karnataka", "january", "february", "march", "april", "may",
    "june", "july", "august", "september", "october", "november",
    "december", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "section", "chapter", "annexure", "schedule",
    "note", "notes", "source", "report", "total", "particulars",
    "electricals", "motors", "traders", "agencies", "distributors",
    "exports", "imports", "textiles", "steels", "engineering", "engineers",
    "consultants", "associates", "chemicals", "plastics", "metals",
    "logistics", "infra", "realty", "developers", "builders", "foods",
    "pharma", "labs", "technologies", "systems", "services", "solutions",
    "ventures", "traders", "mills", "works", "products", "sangathna",
    "sangh", "union", "foundation", "hospital", "college", "school",
    "website", "email", "e-mail", "telephone", "tel", "fax", "sebi", "cin",
    "registration", "contact", "investor", "grievance", "compliance",
    "designation", "din", "address", "branch", "parents", "chairman",
    "huf", "aged", "years", "relationship", "father", "mother", "spouse",
    "the", "and", "independent", "chartered", "engineer", "accountant",
    "accountants", "executive", "managing", "whole", "nominee", "additional",
    "secretary", "personnel", "management", "auditor", "auditors", "advisor",
    "advisors", "consultant", "counsel", "partner", "proprietor", "member",
    "members", "employee", "employees", "staff", "team", "practising",
    "practicing", "registrar", "banker", "lead", "manager", "managers",
}

STREET_KEYWORDS = {
    "road", "rd", "street", "st", "lane", "marg", "path", "avenue", "ave",
    "boulevard", "blvd", "highway", "nagar", "colony", "society", "chowk",
    "cross", "circle", "square", "sector", "phase", "plot", "gat", "survey",
    "khasra", "village", "taluka", "tehsil", "district", "block", "wing",
    "tower", "floor", "flat", "apartment", "apartments", "building",
    "complex", "estate", "park", "premises", "house", "bhavan", "chambers",
    "centre", "center", "campus", "industrial area", "midc", "gidc",
    "peth", "vihar", "puram", "layout", "extension", "bazar", "bazaar",
}

INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand",
    "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
    "meghalaya", "mizoram", "nagaland", "odisha", "punjab", "rajasthan",
    "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh",
    "uttarakhand", "west bengal", "delhi", "new delhi", "puducherry",
    "chandigarh", "jammu and kashmir", "ladakh",
}
