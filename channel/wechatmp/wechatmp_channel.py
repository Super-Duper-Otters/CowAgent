# -*- coding: utf-8 -*-
import asyncio
import imghdr
import io
import os
import threading
import time

import requests
import web
from wechatpy.crypto import WeChatCrypto
from wechatpy.exceptions import WeChatClientException

from bridge.context import *
from bridge.reply import *
from channel.chat_channel import ChatChannel
from channel.wechatmp.common import *
from channel.wechatmp.media_cache import image_media_cache, local_image_media_key
from channel.wechatmp.passive_reply_cache import PassiveReplyCache
from channel.wechatmp.wechatmp_client import WechatMPClient
from common.log import logger
from common.singleton import singleton
from common.utils import split_string_by_utf8_length, remove_markdown_symbol
from config import conf

try:
    from voice.audio_convert import any_to_mp3, split_audio
except ImportError as e:
    logger.debug("import voice.audio_convert failed, voice features will not be supported: {}".format(e))

# If using SSL, uncomment the following lines, and modify the certificate path.
# from cheroot.server import HTTPServer
# from cheroot.ssl.builtin import BuiltinSSLAdapter
# HTTPServer.ssl_adapter = BuiltinSSLAdapter(
#         certificate='/ssl/cert.pem',
#         private_key='/ssl/cert.key')


def discard_passive_reply_cache_by_source(source_type, source_id):
    try:
        cache = WechatMPChannel().cache_dict
        discard = getattr(cache, "discard_by_source", None)
        if not discard:
            return 0
        return discard(source_type, source_id)
    except Exception as exc:
        logger.debug("[wechatmp] discard passive reply cache by source failed: {}".format(exc))
        return 0


@singleton
class WechatMPChannel(ChatChannel):
    def __init__(self, passive_reply=True):
        super().__init__()
        if passive_reply is False:
            logger.warning("[wechatmp] active reply mode is disabled; falling back to passive reply")
        self.passive_reply = True
        self.NOT_SUPPORT_REPLYTYPE = []
        self._http_server = None
        appid = conf().get("wechatmp_app_id")
        secret = conf().get("wechatmp_app_secret")
        token = conf().get("wechatmp_token")
        aes_key = conf().get("wechatmp_aes_key")
        self.client = WechatMPClient(appid, secret)
        self.crypto = None
        if aes_key:
            self.crypto = WeChatCrypto(token, aes_key, appid)
        if self.passive_reply:
            # Cache the reply to the user's first message
            self.cache_dict = PassiveReplyCache()
            # Record whether the current message is being processed
            self.running = set()
            self.technical_analysis_titles = {}
            self.running_started_at = {}
            self.running_lock = threading.RLock()
            # Count the request from wechat official server by message_id
            self.request_cnt = dict()
            # The permanent media need to be deleted to avoid media number limit
            self.delete_media_loop = asyncio.new_event_loop()
            t = threading.Thread(target=self.start_loop, args=(self.delete_media_loop,))
            t.setDaemon(True)
            t.start()

    def queue_active_fallback(self, receiver, reply_type, reply_content):
        logger.warning("[wechatmp] active fallback is disabled; ignore fallback for {}".format(receiver))

    def pop_active_fallback(self, receiver):
        return None

    def mark_active_running(self, receiver):
        logger.warning("[wechatmp] active running state is disabled; ignore mark for {}".format(receiver))

    def try_mark_active_running(self, receiver):
        logger.warning("[wechatmp] active running state is disabled; ignore try_mark for {}".format(receiver))
        return False

    def mark_active_done(self, receiver):
        logger.warning("[wechatmp] active running state is disabled; ignore done for {}".format(receiver))

    def is_active_running(self, receiver):
        return False

    def _wechat_error_text(self, action, exc):
        raw = remove_markdown_symbol(str(exc) or type(exc).__name__)
        if "48001" in raw or "api unauthorized" in raw.lower():
            return "{}失败：微信接口未授权或账号未认证，请检查微信公众平台接口权限。".format(action)
        if len(raw) > 160:
            raw = raw[:160] + "..."
        return "{}失败：{}".format(action, raw)

    def startup(self):
        urls = ("/wx", "channel.wechatmp.passive_reply.Query")
        app = web.application(urls, globals(), autoreload=False)
        port = conf().get("wechatmp_port", 8080)
        func = web.httpserver.StaticMiddleware(app.wsgifunc())
        func = web.httpserver.LogMiddleware(func)
        server = web.httpserver.WSGIServer(("0.0.0.0", port), func)
        self._http_server = server
        try:
            server.start()
        except (KeyboardInterrupt, SystemExit):
            server.stop()

    def stop(self):
        if self._http_server:
            try:
                self._http_server.stop()
                logger.info("[wechatmp] HTTP server stopped")
            except Exception as e:
                logger.warning(f"[wechatmp] Error stopping HTTP server: {e}")
            self._http_server = None

    def start_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _generate_reply(self, context: Context, reply: Reply = Reply()) -> Reply:
        return super()._generate_reply(context, reply)

    def _reply_media_items(self, content):
        if isinstance(content, list):
            return [item for item in content if item]
        return [content]

    def _image_storage_from_path_or_url(self, value):
        if isinstance(value, str) and value.startswith("file://"):
            value = value[7:]
        if isinstance(value, str) and os.path.exists(value):
            image_storage = open(value, "rb")
            image_type = imghdr.what(value) or os.path.splitext(value)[1].lstrip(".") or "png"
            return image_storage, image_type
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            pic_res = requests.get(value, stream=True)
            image_storage = io.BytesIO()
            for block in pic_res.iter_content(1024):
                image_storage.write(block)
            image_storage.seek(0)
            image_type = imghdr.what(image_storage) or "png"
            return image_storage, image_type
        if hasattr(value, "seek"):
            value.seek(0)
            image_type = imghdr.what(value) or "png"
            value.seek(0)
            return value, image_type
        raise ValueError("unsupported image content")

    def _record_investment_delivery_warning(self, request_id, detail):
        if not request_id:
            return
        try:
            from business.business_records import append_delivery_warning

            append_delivery_warning(request_id, detail)
        except Exception as exc:
            logger.warning("[wechatmp] record investment delivery warning failed: {}".format(exc))

    async def delete_media(self, media_id):
        logger.debug("[wechatmp] permanent media {} will be deleted in 10s".format(media_id))
        await asyncio.sleep(10)
        self.client.material.delete(media_id)
        logger.info("[wechatmp] permanent media {} has been deleted".format(media_id))

    def send(self, reply: Reply, context: Context):
        receiver = context["receiver"]
        if self.passive_reply:
            self.cache_dict.cleanup_expired()
            cache_title = context.content if isinstance(context.content, str) else ""
            business_request_id = getattr(reply, "business_request_id", "") or getattr(reply, "investment_request_id", "")
            business_service_type = getattr(reply, "business_service_type", "") or getattr(reply, "investment_service_type", "")
            business_source_type = getattr(reply, "business_source_type", "") or getattr(reply, "investment_source_type", "")
            business_source_id = getattr(reply, "business_source_id", "") or getattr(reply, "investment_source_id", "")
            if reply.type == ReplyType.TEXT or reply.type == ReplyType.INFO or reply.type == ReplyType.ERROR:
                reply_text = remove_markdown_symbol(reply.content)
                logger.info("[wechatmp] text cached, receiver {}\n{}".format(receiver, reply_text))
                self.cache_dict.append_reply(
                    receiver,
                    "text",
                    reply_text,
                    cache_title,
                    service_type=business_service_type,
                    request_id=business_request_id,
                    source_type=business_source_type,
                    source_id=business_source_id,
                )
            elif reply.type == ReplyType.VOICE:
                try:
                    voice_file_path = reply.content
                    duration, files = split_audio(voice_file_path, 60 * 1000)
                    if len(files) > 1:
                        logger.info("[wechatmp] voice too long {}s > 60s , split into {} parts".format(duration / 1000.0, len(files)))

                    for path in files:
                        # support: <2M, <60s, mp3/wma/wav/amr
                        try:
                            with open(path, "rb") as f:
                                response = self.client.material.add("voice", f)
                                logger.debug("[wechatmp] upload voice response: {}".format(response))
                                f_size = os.fstat(f.fileno()).st_size
                                time.sleep(1.0 + 2 * f_size / 1024 / 1024)
                                # todo check media_id
                        except WeChatClientException as e:
                            logger.error("[wechatmp] upload voice failed: {}".format(e))
                            return
                        media_id = response["media_id"]
                        logger.info("[wechatmp] voice uploaded, receiver {}, media_id {}".format(receiver, media_id))
                        self.cache_dict.append_reply(
                            receiver,
                            "voice",
                            media_id,
                            cache_title,
                            service_type=business_service_type,
                            request_id=business_request_id,
                            source_type=business_source_type,
                            source_id=business_source_id,
                        )
                except ImportError as e:
                    logger.error("[wechatmp] voice conversion failed: {}".format(e))
                    logger.error("[wechatmp] please install pydub: pip install pydub")
                    return

            elif reply.type in (ReplyType.IMAGE_URL, ReplyType.IMAGE):  # 从网络或本地文件读取图片
                uploaded_media_ids = []
                for image_content in self._reply_media_items(reply.content):
                    media_cache_key = local_image_media_key(image_content)
                    cached_media_id = image_media_cache.get(media_cache_key)
                    if cached_media_id:
                        logger.info("[wechatmp] image media cache hit, receiver {}, media_id {}".format(receiver, cached_media_id))
                        uploaded_media_ids.append(cached_media_id)
                        continue
                    image_storage, image_type = self._image_storage_from_path_or_url(image_content)
                    filename = receiver + "-" + str(context["msg"].msg_id) + "." + image_type
                    content_type = "image/" + image_type
                    try:
                        response = self.client.media.upload("image", (filename, image_storage, content_type))
                        logger.debug("[wechatmp] upload image response: {}".format(response))
                    except WeChatClientException as e:
                        warning = self._wechat_error_text("图片上传", e)
                        logger.error("[wechatmp] upload image failed: {}".format(e))
                        self._record_investment_delivery_warning(business_request_id, warning)
                        self.cache_dict.discard_result(receiver)
                        return
                    finally:
                        local_image_path = image_content[7:] if isinstance(image_content, str) and image_content.startswith("file://") else image_content
                        if isinstance(local_image_path, str) and os.path.exists(local_image_path):
                            image_storage.close()
                    media_id = response["media_id"]
                    image_media_cache.set(media_cache_key, media_id)
                    logger.info("[wechatmp] image uploaded, receiver {}, media_id {}".format(receiver, media_id))
                    uploaded_media_ids.append(media_id)
                try:
                    for media_id in uploaded_media_ids:
                        self.cache_dict.append_reply(
                            receiver,
                            "image",
                            media_id,
                            cache_title,
                            service_type=business_service_type,
                            request_id=business_request_id,
                            source_type=business_source_type,
                            source_id=business_source_id,
                        )
                except Exception as e:
                    logger.error("[wechatmp] cache image failed: {}".format(e))
                    self.cache_dict.discard_result(receiver)
                    return
            elif reply.type == ReplyType.VIDEO_URL:  # 从网络下载视频
                video_url = reply.content
                video_res = requests.get(video_url, stream=True)
                video_storage = io.BytesIO()
                for block in video_res.iter_content(1024):
                    video_storage.write(block)
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.material.add("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                media_id = response["media_id"]
                logger.info("[wechatmp] video uploaded, receiver {}, media_id {}".format(receiver, media_id))
                self.cache_dict.append_reply(
                    receiver,
                    "video",
                    media_id,
                    cache_title,
                    service_type=business_service_type,
                    request_id=business_request_id,
                    source_type=business_source_type,
                    source_id=business_source_id,
                )

            elif reply.type == ReplyType.VIDEO:  # 从文件读取视频
                video_storage = reply.content
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.material.add("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                media_id = response["media_id"]
                logger.info("[wechatmp] video uploaded, receiver {}, media_id {}".format(receiver, media_id))
                self.cache_dict.append_reply(
                    receiver,
                    "video",
                    media_id,
                    cache_title,
                    service_type=business_service_type,
                    request_id=business_request_id,
                    source_type=business_source_type,
                    source_id=business_source_id,
                )

        else:
            if reply.type == ReplyType.TEXT or reply.type == ReplyType.INFO or reply.type == ReplyType.ERROR:
                reply_text = reply.content
                texts = split_string_by_utf8_length(reply_text, MAX_UTF8_LEN)
                if len(texts) > 1:
                    logger.info("[wechatmp] text too long, split into {} parts".format(len(texts)))
                try:
                    for i, text in enumerate(texts):
                        self.client.message.send_text(receiver, text)
                        if i != len(texts) - 1:
                            time.sleep(0.5)  # 休眠0.5秒，防止发送过快乱序
                except Exception as e:
                    logger.error("[wechatmp] active text send failed, queue passive fallback for {}: {}".format(receiver, e))
                    self.queue_active_fallback(receiver, "text", reply_text)
                    return
                logger.info("[wechatmp] Do send text to {}: {}".format(receiver, reply_text))
            elif reply.type == ReplyType.VOICE:
                try:
                    file_path = reply.content
                    file_name = os.path.basename(file_path)
                    file_type = os.path.splitext(file_name)[1]
                    if file_type == ".mp3":
                        file_type = "audio/mpeg"
                    elif file_type == ".amr":
                        file_type = "audio/amr"
                    else:
                        mp3_file = os.path.splitext(file_path)[0] + ".mp3"
                        any_to_mp3(file_path, mp3_file)
                        file_path = mp3_file
                        file_name = os.path.basename(file_path)
                        file_type = "audio/mpeg"
                    logger.info("[wechatmp] file_name: {}, file_type: {} ".format(file_name, file_type))
                    media_ids = []
                    duration, files = split_audio(file_path, 60 * 1000)
                    if len(files) > 1:
                        logger.info("[wechatmp] voice too long {}s > 60s , split into {} parts".format(duration / 1000.0, len(files)))
                    for path in files:
                        # support: <2M, <60s, AMR\MP3
                        response = self.client.media.upload("voice", (os.path.basename(path), open(path, "rb"), file_type))
                        logger.debug("[wechatcom] upload voice response: {}".format(response))
                        media_ids.append(response["media_id"])
                        os.remove(path)
                except ImportError as e:
                    logger.error("[wechatmp] voice conversion failed: {}".format(e))
                    logger.error("[wechatmp] please install pydub: pip install pydub")
                    return
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload voice failed: {}".format(e))
                    return

                try:
                    os.remove(file_path)
                except Exception:
                    pass

                for media_id in media_ids:
                    self.client.message.send_voice(receiver, media_id)
                    time.sleep(1)
                logger.info("[wechatmp] Do send voice to {}".format(receiver))
            elif reply.type in (ReplyType.IMAGE_URL, ReplyType.IMAGE):  # 从网络或本地文件读取图片
                for image_content in self._reply_media_items(reply.content):
                    try:
                        image_storage, image_type = self._image_storage_from_path_or_url(image_content)
                    except Exception as e:
                        logger.error("[wechatmp] load image failed: {}".format(e))
                        self.queue_active_fallback(receiver, "text", self._wechat_error_text("图片读取", e))
                        continue
                    filename = receiver + "-" + str(context["msg"].msg_id) + "." + image_type
                    content_type = "image/" + image_type
                    try:
                        response = self.client.media.upload("image", (filename, image_storage, content_type))
                        logger.debug("[wechatmp] upload image response: {}".format(response))
                    except Exception as e:
                        logger.error("[wechatmp] upload image failed: {}".format(e))
                        self.queue_active_fallback(receiver, "text", self._wechat_error_text("图片上传", e))
                        continue
                    try:
                        self.client.message.send_image(receiver, response["media_id"])
                    except Exception as e:
                        logger.error("[wechatmp] active image send failed, queue passive fallback for {}: {}".format(receiver, e))
                        media_id = response.get("media_id")
                        if media_id:
                            self.queue_active_fallback(receiver, "image", media_id)
                        else:
                            self.queue_active_fallback(receiver, "text", self._wechat_error_text("图片发送", e))
                        continue
                    logger.info("[wechatmp] Do send image to {}".format(receiver))
            elif reply.type == ReplyType.VIDEO_URL:  # 从网络下载视频
                video_url = reply.content
                video_res = requests.get(video_url, stream=True)
                video_storage = io.BytesIO()
                for block in video_res.iter_content(1024):
                    video_storage.write(block)
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.media.upload("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                self.client.message.send_video(receiver, response["media_id"])
                logger.info("[wechatmp] Do send video to {}".format(receiver))
            elif reply.type == ReplyType.VIDEO:  # 从文件读取视频
                video_storage = reply.content
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.media.upload("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                self.client.message.send_video(receiver, response["media_id"])
                logger.info("[wechatmp] Do send video to {}".format(receiver))
        return

    def _success_callback(self, session_id, context, **kwargs):  # 线程异常结束时的回调函数
        logger.debug("[wechatmp] Success to generate reply, msgId={}".format(context["msg"].msg_id))
        if self.passive_reply:
            with self.running_lock:
                self.running.discard(session_id)
                self.running_started_at.pop(session_id, None)
                self.technical_analysis_titles.pop(session_id, None)
        else:
            self.mark_active_done(session_id)

    def _fail_callback(self, session_id, exception, context, **kwargs):  # 线程异常结束时的回调函数
        logger.exception("[wechatmp] Fail to generate reply to user, msgId={}, exception={}".format(context["msg"].msg_id, exception))
        if self.passive_reply:
            self.cache_dict.discard_result(session_id)
            with self.running_lock:
                self.running.discard(session_id)
                self.running_started_at.pop(session_id, None)
                self.technical_analysis_titles.pop(session_id, None)
        else:
            from business.constants import ErrorCode, user_message

            self.queue_active_fallback(session_id, "text", user_message(ErrorCode.SYSTEM_ERROR))
            self.mark_active_done(session_id)
