"""
Trend scoring engine for product auto-import.

Scores product candidates 0-100 based on:
  - Brand recognition (0-30)
  - Category demand (0-30)
  - Price optimal range (0-20)
  - Name quality / spec presence (0-10)
  - Exclusivity / margin potential (0-10)

Optional: web presence via urllib (Bing search result count).

Usage:
    from trending import score_product, TREND_THRESHOLD
    result = score_product("JBL GO4 ORIGINAL", costo=55_480)
"""

import re
import unicodedata
import urllib.request
import urllib.parse
import json
import ssl

# ─── Brand scoring (0-30) ───

BRAND_SCORES = {
    "SAMSUNG": 30,
    "APPLE": 30,
    "JBL": 28,
    "SONY": 28,
    "XIAOMI": 28,
    "REDMI": 27,
    "POCO": 25,
    "TCL": 25,
    "NINTENDO": 28,
    "XBOX": 26,
    "PLAYSTATION": 26,
    "PS5": 26,
    "BGH": 20,
    "NOGA": 18,
    "NOGA TORNADO": 20,
    "NOGA DRIFTER": 22,
    "HISENSE": 22,
    "PHILCO": 18,
    "NOBLEX": 18,
    "ATVIO": 15,
    "GADNIC": 15,
    "NUVOH": 12,
    "NURIK": 10,
    "NOMADE": 12,
    "SIERA": 10,
    "ENOVA": 12,
    "KEN BROWN": 14,
    "PIONEER": 22,
    "SPRINT": 5,
    "LAMBORGHINI": 20,
    "DAIHATSU": 15,
    "CECOTEC": 18,
    "WINCO": 10,
    "STROMBERG": 18,
    "HYUNDAI": 20,
    "KALLEY": 8,
    "OVNS": 5,
    "SUPREME": 5,
    "GEEK BAR": 3,
    "EMBASSY": 8,
    "TELEFUNKEN": 14,
    "LUSQTOFF": 5,
}

def _detect_brand(name):
    """Detect brand in product name and return (brand, score)."""
    name_upper = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().upper()
    name_upper = re.sub(r'[^\w\s]', ' ', name_upper)
    
    # Normalize spaces
    name_upper = re.sub(r'\s+', ' ', name_upper).strip()
    
    # Try exact brand matches with word boundaries (longer = more specific = higher priority)
    matches = []
    for brand, score in sorted(BRAND_SCORES.items(), key=lambda x: -len(x[0])):
        pattern = r'\b' + re.escape(brand) + r'\b'
        if re.search(pattern, name_upper):
            matches.append((brand, score))
    
    if matches:
        return matches[0]
    
    # Generic brands detection with word boundaries
    for brand_key in ["LG", "MOTOROLA", "LENOVO", "DELL", "ASUS"]:
        if re.search(r'\b' + re.escape(brand_key) + r'\b', name_upper):
            return (brand_key, 25)
    
    # Special: "HP" must be followed by letter/dash (not just standalone)
    if re.search(r'\bHP\b', name_upper):
        return ("HP", 25)
    # "ACER" must be word-boundary protected
    if re.search(r'\bACER\b', name_upper):
        return ("ACER", 25)
    # "PHILIPS" word boundary
    if re.search(r'\bPHILIPS\b', name_upper):
        return ("PHILIPS", 25)
    
    # AirPods = Apple
    if "AIRPOD" in name_upper:
        return ("APPLE", 30)
    # Galaxy Buds = Samsung
    if "GALAXY BUDS" in name_upper or "BUDS PRO" in name_upper:
        return ("SAMSUNG", 28)
    # HP headphones
    if re.search(r'\bHP H\d', name_upper):
        return ("HP", 25)
    
    return (None, 0)


# ─── Category scoring (0-30) ───

CATEGORY_SCORES = [
    (r'\b(airpod\w*|auricular|galaxy\s*buds|jbl|parlante|bocina|headphone|headset|buds\s+pro)\b', 30, "Audio"),
    (r'\b(smartphone|celular|telefono|samsung\s+\w+|xiaomi|redmi|poco|tcl\s*\w+|motorola|iphone)\b', 30, "Smartphones"),
    (r'\b(smart\s*tv|tv\s+\w+|televisor|\d{2,}\s*["""]?)\b', 28, "Smart TV"),
    (r'\b(xbox|playstation|ps\d|nintendo|switch|consola|volante|joystick)\b', 28, "Gaming"),
    (r'\b(notebook|netbook|laptop)\b', 26, "Computación"),
    (r'\b(proyector|proyector|proyector\s+gamer)\b', 24, "Proyectores"),
    (r'\b(cafetera|pava|termo|mate)\b', 22, "Hogar"),
    (r'\b(estufa|calefactor|calefaccion|halogena|garrafera|pioneer)\b', 20, "Hogar"),
    (r'\b(bicicleta|monopatin|bici)\b', 20, "Deportes"),
    (r'\b(freidora|microondas|lavarropa|secarropa|aspiradora|licuadora|batidora|tostadora|waflera|mixer|anafe)\b', 18, "Electrohogar"),
    (r'\b(sillon|sill[oó]n|mueble|escritorio|mesa|silla)\b', 14, "Hogar"),
    (r'\b(cava|vino|vinoteca)\b', 12, "Hogar"),
    (r'\b(vape|vapers|vapor|dummy|geek\s*bar|supreme|ovns)\b', 2, "Vapes"),
    (r'\b(crema|cosmetica|maquillaje|shampoo|acondicionador|karseell)\b', 8, "Belleza"),
    (r'\b(spray|copa\s+mundo|cotillon|decoracion)\b', 3, "Eventos"),
    (r'\b(pochoclera|pochoclo|popcorn|palomita)\b', 8, "Hogar"),
    (r'\b(tender|tendedero|secador|lavadero)\b', 6, "Lavadero"),
    (r'\b(compresor|inflador|herramienta)\b', 8, "Herramientas"),
    (r'\b(cargador|cable|adaptador|usb|hub|bater[ií]a|power\s*bank)\b', 18, "Accesorios"),
]


def _score_category(name):
    """Score product based on its category."""
    name_lower = name.lower()
    name_lower = unicodedata.normalize('NFKD', name_lower).encode('ascii', 'ignore').decode().lower()
    
    best_score = 10  # default for "General"
    best_cat = "General"
    
    for pattern, score, cat in CATEGORY_SCORES:
        if re.search(pattern, name_lower):
            if score > best_score:
                best_score = score
                best_cat = cat
    
    return best_score, best_cat


# ─── Price scoring (0-20) ───

def _score_price(costo):
    """Score based on optimal price range for resale in Argentina.
    Sweet spot: $15K - $500K (accessible but decent margin)."""
    if not costo or costo <= 0:
        return 5
    
    # Under $5K - very cheap, low margin
    if costo < 5000:
        return 5
    # $5K - $15K - cheap, but can work in volume
    if costo < 15000:
        return 10
    # $15K - $60K - sweet spot low
    if costo < 60000:
        return 18
    # $60K - $200K - sweet spot mid
    if costo < 200000:
        return 20
    # $200K - $500K - sweet spot high
    if costo < 500000:
        return 18
    # $500K - $1M - premium, good margin
    if costo < 1000000:
        return 14
    # $1M+ - high ticket, fewer buyers but higher margin potential
    if costo < 3000000:
        return 12
    # Very expensive
    return 8


# ─── Name quality scoring (0-10) ───

def _score_name_quality(name):
    """Score how specific/identifiable the product name is."""
    n = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().upper()
    score = 5  # base
    
    # Has model number (A15, C75, 4K, XS, etc.)
    if re.search(r'\b[A-Z]\d{2,}\b', n):
        score += 2
    # Has storage size
    if re.search(r'\b\d+\s*(GB|TB|RAM)\b', n):
        score += 1
    # Has brand
    brand, _ = _detect_brand(name)
    if brand:
        score += 1
    # Has color
    if re.search(r'\b(NEGRO|BLANCO|AZUL|ROJO|VERDE|DORADO|PLATEADO)\b', n):
        score += 1
    
    return min(score, 10)


# ─── Exclusivity / margin scoring (0-10) ───

def _score_exclusividad(name):
    """Score how exclusive/distinctive the product is (less commoditized = more margin)."""
    n = name.upper()
    score = 5  # base
    
    # Very commoditized products (lower score)
    if re.search(r'\b(AIRPODS|GALAXY\s+BUDS|JBL\s+(GO|CLIP|GRIP))\b', n):
        score -= 2
    if re.search(r'\b(XBOX|PLAYSTATION|PS5)\b', n):
        score -= 1
    if re.search(r'\b(SILLA\s+PLEGABLE|TENDER|DUMMY|SPRAY)\b', n):
        score -= 3
    if re.search(r'\b(REMERA|MOUSE|CABLE|CARGADOR)\b', n):
        score -= 2
    
    # More exclusive products (higher score)
    if re.search(r'\b(PROYECTOR|DRIFTER|VOLANTE|SILLON|TEDDY|ESTUFA\s+GARRAFERA|NXTPAPER)\b', n):
        score += 2
    if re.search(r'\b(ULTRA|S25|BUDS\s+PRO|QUIET\s+ANC|TORNADO)\b', n):
        score += 1
    if re.search(r'\b(NOTEBOOK|LAPTOP|BICICLETA|MONOPATIN)\b', n):
        score += 1
    
    return max(0, min(score, 10))


# ─── Optional: Web presence score (requires urllib, may add latency) ───

def _buscar_en_bing(query, max_retries=1):
    """Search Bing and return approximate result count. May return None on failure."""
    try:
        ctx = ssl.create_default_context()
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count=1"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        resp = urllib.request.urlopen(req, timeout=8, context=ctx)
        html = resp.read().decode("utf-8", errors="replace")
        
        # Bing shows "APROXIMADAMENTE X RESULTADOS" or similar
        m = re.search(r'(?:aproximadamente|cerca de|alrededor de|about)\s+([\d.,]+)\s+(?:resultados?|results?)', html, re.IGNORECASE)
        if m:
            count = int(m.group(1).replace(",", "").replace(".", ""))
            return count
        
        # Alternative: count of results shown
        m = re.search(r'id="b_tBetween"[^>]*>([\d.,]+)', html)
        if m:
            count = int(m.group(1).replace(",", "").replace(".", ""))
            return count
        
        return None
    except Exception:
        return None


def _score_web_presence(name):
    """Score based on Bing search result count. Returns (score, count)."""
    try:
        result_count = _buscar_en_bing(name)
        if result_count is None:
            return (10, None)  # neutral if can't determine
        
        if result_count > 100000:
            return (20, result_count)
        elif result_count > 50000:
            return (18, result_count)
        elif result_count > 10000:
            return (15, result_count)
        elif result_count > 5000:
            return (12, result_count)
        elif result_count > 1000:
            return (8, result_count)
        elif result_count > 100:
            return (5, result_count)
        else:
            return (2, result_count)
    except Exception:
        return (10, None)


# ─── Main scoring function ───

TREND_THRESHOLD = 60  # 0-100, products below this are flagged for manual review

def score_product(name, costo=None, use_web=False):
    """
    Score a product candidate for trending potential.
    
    Returns:
        dict with keys: total, brand, category, price, name_quality, 
                        exclusividad, web_presence, web_count, category_name
    """
    brand, brand_score = _detect_brand(name)
    cat_score, cat_name = _score_category(name)
    price_score = _score_price(costo)
    name_score = _score_name_quality(name)
    excl_score = _score_exclusividad(name)
    
    result = {
        "total": brand_score + cat_score + price_score + name_score + excl_score,
        "brand": brand_score,
        "category": cat_score,
        "price": price_score,
        "name_quality": name_score,
        "exclusividad": excl_score,
        "web_presence": 0,
        "web_count": None,
        "category_name": cat_name,
        "brand_name": brand or "Genérico",
    }
    
    if use_web:
        web_score, count = _score_web_presence(name)
        result["web_presence"] = web_score
        result["web_count"] = count
        # Normalize: if web is used, reduce other weights proportionally
        result["total"] = brand_score + cat_score + price_score + name_score + excl_score + web_score
        # Rebalance for 0-100 scale
        result["total"] = int(result["total"] * 100 / 120)
    else:
        # Scale to 0-100
        result["total"] = int(result["total"] * 100 / 100)
    
    result["total"] = max(0, min(100, result["total"]))
    
    return result


def is_trending(name, costo=None, threshold=TREND_THRESHOLD, use_web=False):
    """
    Quick check: is this product worth auto-importing?
    Returns (bool, score_dict)
    """
    score = score_product(name, costo, use_web)
    return score["total"] >= threshold, score


def format_score(score_dict):
    """Format score for console output."""
    total = score_dict["total"]
    
    if total >= 80:
        bar = "🟢🟢🟢🟢🟢"
    elif total >= 60:
        bar = "🟢🟢🟢🟢⚪"
    elif total >= 40:
        bar = "🟡🟡🟡⚪⚪"
    elif total >= 20:
        bar = "🟠🟠⚪⚪⚪"
    else:
        bar = "🔴⚪⚪⚪⚪"
    
    note = ""
    if total >= TREND_THRESHOLD:
        note = " ✓ TRENDING"
    else:
        note = " ⚠ REVISAR"
    
    web = ""
    if score_dict["web_count"]:
        web = f" | web: {score_dict['web_count']:,} resultados"
    
    return (
        f"  {bar}  {total}/100{note}  "
        f"[{score_dict['brand_name']} | {score_dict['category_name']}]{web}"
    )


def suggest_margen(name, categoria=None):
    """Suggest optimal margin based on product category."""
    name_upper = name.upper()
    
    # Premium electronics = lower margin (competition)
    if any(b in name_upper for b in ["JBL", "SAMSUNG", "APPLE", "XBOX", "PLAYSTATION", "SONY", "NINTENDO"]):
        return 30
    # Phones (competitive)
    if any(b in name_upper for b in ["XIAOMI", "REDMI", "POCO", "TCL", "MOTOROLA"]):
        return 28
    # TVs and large appliances (low margin, high ticket)
    if any(t in name_upper for t in ["TV ", "SMART TV", "TELEVISOR"]):
        return 25
    # Audio accessories (good margin)
    if any(a in name_upper for a in ["AURICULAR", "BUDS", "AIRPODS", "PARLANTE"]):
        return 35
    # Gaming accessories
    if any(g in name_upper for g in ["VOLANTE", "SILLA GAMER", "PROYECTOR"]):
        return 35
    # Generic / house brands
    if any(b in name_upper for b in ["NUVOH", "NOMADE", "GADNIC", "SIERA", "ENOVA", "WINCO"]):
        return 38
    
    return 35  # default


if __name__ == "__main__":
    import sys
    
    test_products = [
        ("JBL GO4 ORIGINAL", 55480),
        ("SAMSUNG GALAXY S25 ULTRA 256GB", 1756800),
        ("XBOX SERIES X 1TB", 1249500),
        ("AIRPODS PRO", 40000),
        ("SILLA PLEGABLE", 30990),
        ("SPRAY COPA DEL MUNDO", 2500),
        ("CREMAS KARSEELL ORIGINALES", 12665),
        ("GEEK BAR", 13230),
        ("TENDER NUVOH", 19845),
        ("NOTEBOOK ENOVA 14 CELERON", 325000),
        ("CAVA DE VINO WINCO", 215000),
        ("POCHOCLERA WINCO 1200W", 43800),
        ("COMPRESOR DE AIRE", 23920),
    ]
    
    print(f"{'PRODUCTO':<55} {'SCORE':<8} {'TRENDING?':<10}")
    print("-" * 75)
    for name, costo in test_products:
        score = score_product(name, costo)
        trending, _ = is_trending(name, costo)
        print(f"{name:<55} {score['total']:<8} {'✓' if trending else '✗'}")
        print(f"         → {format_score(score)}")
