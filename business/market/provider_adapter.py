# encoding:utf-8
import re
from dataclasses import dataclass


MAINLAND_PROVIDER_ASSET_TYPES = {"a_share", "index", "etf", "convertible_bond"}
FUTURES_SYMBOLS = {"T0", "TL0", "TF0", "TS0", "T", "TL", "TF", "TS"}


@dataclass(frozen=True)
class AssetTarget:
    raw_symbol: str
    normalized_code: str
    asset_type: str = ""
    market: str = ""
    ts_code: str = ""


def classify_asset_target(
    symbol: str,
    *,
    asset_type: str = "",
    market: str = "",
    ts_code: str = "",
) -> AssetTarget:
    raw = str(symbol or "").strip()
    normalized = _normalize_code(ts_code or raw)
    explicit_asset = _normalize_asset_type(asset_type)
    explicit_market = _normalize_market(market)
    bare = bare_symbol(normalized)
    upper = normalized.upper()
    lower = normalized.lower()

    inferred_market = explicit_market
    inferred_asset = explicit_asset
    if not inferred_market:
        inferred_market = _market_from_symbol(normalized)
    if not inferred_asset:
        if re.fullmatch(r"(sh|sz|bj)\d{6}", lower):
            inferred_asset = "index"
        elif upper.endswith(".CSI"):
            inferred_asset = "index"
        elif upper.endswith(".HK") or re.fullmatch(r"HK\d{5}", upper):
            inferred_asset = "hk_stock"
        elif upper.endswith(".US"):
            inferred_asset = "us_stock"
        elif upper in FUTURES_SYMBOLS:
            inferred_asset = "futures"
        elif upper.endswith((".SH", ".SZ")):
            if len(bare) == 6 and bare.startswith(("51", "15")):
                inferred_asset = "etf"
            elif len(bare) == 6 and bare.startswith(("11", "12")):
                inferred_asset = "convertible_bond"
            else:
                inferred_asset = "a_share"
        elif upper.endswith(".BJ") and len(bare) == 6 and bare.startswith("81"):
            inferred_asset = "convertible_bond"
        elif len(bare) == 6 and bare.isdigit():
            inferred_asset = "a_share"

    return AssetTarget(
        raw_symbol=raw,
        normalized_code=normalized,
        asset_type=inferred_asset,
        market=inferred_market,
        ts_code=_normalize_code(ts_code or normalized),
    )


def bare_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    upper = text.upper()
    if upper.startswith("HK") and upper[2:].isdigit():
        return upper[2:]
    if "." in text:
        return text.split(".", 1)[0]
    return re.sub(r"^(sh|sz|bj)", "", text, flags=re.IGNORECASE)


def to_akshare_symbol(target: AssetTarget) -> str:
    bare = bare_symbol(target.normalized_code)
    if target.asset_type == "index" and target.normalized_code.upper().endswith(".CSI") and re.fullmatch(r"H\d{5}", bare.upper()):
        bare = bare[1:]
    if target.asset_type in {"index", "etf", "convertible_bond"}:
        return f"{_mainland_prefix(target)}{bare}".lower() if bare else ""
    if target.asset_type == "a_share":
        return bare
    if target.asset_type == "hk_stock":
        return bare.zfill(5)
    if target.asset_type == "us_stock":
        return bare.upper()
    if target.asset_type == "futures":
        return target.normalized_code.upper()
    return bare


def to_tushare_symbol(target: AssetTarget) -> str:
    if target.asset_type in {"hk_stock", "us_stock", "futures"}:
        return target.ts_code or target.normalized_code
    if target.asset_type in {"a_share", "index", "etf", "convertible_bond"}:
        return _suffix_mainland_code(target)
    return target.ts_code or target.normalized_code


def to_baostock_symbol(target: AssetTarget) -> str:
    if target.asset_type not in MAINLAND_PROVIDER_ASSET_TYPES:
        return ""
    bare = bare_symbol(target.normalized_code)
    if target.asset_type == "index" and target.normalized_code.upper().endswith(".CSI") and re.fullmatch(r"H\d{5}", bare.upper()):
        return ""
    if not bare:
        return ""
    return f"{_mainland_prefix(target)}.{bare}".lower()


def provider_capabilities(target: AssetTarget) -> dict[str, bool]:
    return {
        "akshare": bool(to_akshare_symbol(target)),
        "tushare": bool(to_tushare_symbol(target)),
        "baostock": bool(to_baostock_symbol(target)),
    }


def _normalize_code(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", text, flags=re.IGNORECASE):
        return text.lower()
    return text.upper()


def _normalize_asset_type(value: str) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "stock": "a_share",
        "a": "a_share",
        "hk": "hk_stock",
        "hongkong": "hk_stock",
        "us": "us_stock",
        "fund": "etf",
        "cb": "convertible_bond",
        "bond": "convertible_bond",
    }
    return aliases.get(text, text)


def _normalize_market(value: str) -> str:
    text = str(value or "").strip().upper()
    aliases = {"SSE": "SH", "SZSE": "SZ"}
    return aliases.get(text, text)


def _market_from_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    upper = text.upper()
    lower = text.lower()
    if re.fullmatch(r"sh\d{6}", lower):
        return "SH"
    if re.fullmatch(r"sz\d{6}", lower):
        return "SZ"
    if re.fullmatch(r"bj\d{6}", lower):
        return "BJ"
    if upper.endswith(".CSI"):
        return "CSI"
    if upper.endswith(".SH"):
        return "SH"
    if upper.endswith(".SZ"):
        return "SZ"
    if upper.endswith(".BJ"):
        return "BJ"
    if upper.endswith(".HK") or upper.startswith("HK"):
        return "HK"
    if upper.endswith(".US"):
        return "US"
    if upper in FUTURES_SYMBOLS:
        return "CFFEX"
    return ""


def _mainland_prefix(target: AssetTarget) -> str:
    market = _normalize_market(target.market)
    if market in {"SH", "CSI"}:
        return "sh"
    if market == "SZ":
        return "sz"
    if market == "BJ":
        return "bj"
    upper = target.normalized_code.upper()
    if upper.endswith((".SH", ".CSI")):
        return "sh"
    if upper.endswith(".SZ"):
        return "sz"
    if upper.endswith(".BJ"):
        return "bj"
    lower = target.normalized_code.lower()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", lower):
        return lower[:2]
    bare = bare_symbol(target.normalized_code)
    return "sh" if bare.startswith(("5", "6", "9")) else "sz"


def _suffix_mainland_code(target: AssetTarget) -> str:
    upper = target.ts_code.upper() if target.ts_code else target.normalized_code.upper()
    if re.fullmatch(r"H\d{5}\.CSI", upper):
        return upper
    if upper.endswith(".CSI"):
        return upper
    if re.fullmatch(r"\d{6}\.(SH|SZ|BJ|CSI)", upper):
        return upper
    lower = upper.lower()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", lower):
        prefix = lower[:2].upper()
        return f"{lower[2:]}.{prefix}"
    bare = bare_symbol(upper)
    if not bare:
        return upper
    prefix = _mainland_prefix(target).upper()
    return f"{bare}.{prefix}"
