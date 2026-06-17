# encoding:utf-8


def prepare_technical_analysis_business_context(raw_input: str, target_text: str):
    from business.technical_analysis import prepare_technical_analysis_cache_context

    return prepare_technical_analysis_cache_context(raw_input, target_text)


def run_technical_analysis_business(openid: str, raw_input: str, target_text: str, *, cache_context=None):
    from business.technical_analysis import run_technical_analysis

    return run_technical_analysis(openid, raw_input, target_text, cache_context=cache_context)
