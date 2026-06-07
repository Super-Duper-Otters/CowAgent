# encoding:utf-8


def handle_inbound_message(openid: str, content: str, input_type: str = "text", attachments=None):
    from . import router
    from .constants import ServiceType

    if input_type != "text":
        return router.BusinessReply(
            False,
            False,
            router.DEFAULT_UNMATCHED_PROMPT,
            [],
            ServiceType.UNMATCHED,
        )
    return router.handle_text_message(openid, content)
