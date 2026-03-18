"""
텔레그램 명령어 폴링 (백그라운드 스레드)

지원 명령어:
  /status  — 현재 잔고 + 포지션 현황
  /pnl     — 누적/오늘 손익 + 승률
"""
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Callable

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


class CommandPoller(threading.Thread):
    def __init__(self, token: str, chat_id: str, get_reply_fn: Callable[[str], str],
                 extra_chat_id: str = ""):
        super().__init__(daemon=True, name="TelegramCommands")
        self.token      = token
        self.allowed    = {str(chat_id)}
        if extra_chat_id:
            self.allowed.add(str(extra_chat_id))
        self.get_reply  = get_reply_fn
        self.offset     = 0
        self._base      = f"https://api.telegram.org/bot{token}"

    def _send(self, chat_id: str, text: str):
        try:
            requests.post(
                f"{self._base}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"[커맨드봇] 전송 실패: {e}")

    def run(self):
        logger.info("[커맨드봇] 폴링 시작 (/status, /pnl)")
        while True:
            try:
                resp = requests.get(
                    f"{self._base}/getUpdates",
                    params={"offset": self.offset, "timeout": 30},
                    timeout=35,
                )
                data = resp.json()
                if not data.get("ok"):
                    time.sleep(5)
                    continue
                for update in data.get("result", []):
                    self.offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    incoming_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip()
                    logger.info(f"[커맨드봇] 수신: chat_id={incoming_id} text={text!r}")
                    if incoming_id not in self.allowed:
                        logger.warning(f"[커맨드봇] chat_id 불일치: {incoming_id}")
                        continue
                    if not text:
                        continue
                    # /status@botname 형식도 처리
                    cmd = text.split()[0].split("@")[0].lower()
                    if cmd in ("/status", "/pnl"):
                        try:
                            self._send(incoming_id, self.get_reply(cmd))
                        except Exception as e:
                            logger.warning(f"[커맨드봇] 응답 생성 실패: {e}")
                            self._send(incoming_id, "⚠️ 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
            except requests.exceptions.Timeout:
                pass  # 롱폴링 정상 타임아웃
            except Exception as e:
                logger.warning(f"[커맨드봇] 폴링 오류: {e}")
                time.sleep(5)
