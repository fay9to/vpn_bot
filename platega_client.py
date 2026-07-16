# platega_client.py
import httpx
import hashlib
import logging
import config

logger = logging.getLogger(__name__)


class PlategaClient:
    def __init__(self):
        # В Bedolaga и Platega v2 используется именно shopId, а не merchantId
        self.shop_id = config.PLATEGA_SHOP_ID
        self.secret = config.PLATEGA_SECRET
        self.base_url = (config.PLATEGA_BASE_URL or 'https://app.platega.io').rstrip('/')

    def _generate_signature(self, shop_id: str, amount: float, order_id: str) -> str:
        """Генерирует MD5 подпись для Platega"""
        amount_str = f"{amount:.2f}" if isinstance(amount, float) else str(amount)
        message = f"{shop_id}{amount_str}{order_id}"
        return hashlib.md5((message + self.secret).encode('utf-8')).hexdigest()

    async def create_payment(
            self,
            order_id: str,
            amount: float,
            description: str,
            email: str = "",
            payment_method: int = 11  # 11 = Карта + СБП
    ) -> dict:
        if not self.shop_id or not self.secret:
            return {"success": False, "error": "Platega не настроен: проверьте PLATEGA_SHOP_ID и PLATEGA_SECRET в .env"}

        url = f"{self.base_url}/v2/transaction/process"

        # Генерируем подпись
        signature = self._generate_signature(self.shop_id, amount, order_id)

        # СТРОГОЕ соответствие структуре Bedolaga / Platega v2
        payload = {
            "shopId": self.shop_id,  # <-- БЫЛО merchantId, СТАЛО shopId (это была причина ошибки!)
            "amount": round(amount, 2),
            "currency": "RUB",
            "orderId": order_id,
            "description": description[:64],
            "email": email,
            "paymentMethod": payment_method,
            "language": "ru",
            "signature": signature,
            "returnUrl": "https://t.me/cerberusVPN_robot",
            "failUrl": "https://t.me/cerberusVPN_robot",
            "paymentDetails": {  # <-- Обязательно вложенный объект
                "amount": round(amount, 2),
                "currency": "RUB"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            logger.info(f"🎯 Запрос к Platega: {url}")
            logger.info(f"📤 Payload: {payload}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                raw_text = response.text
                logger.info(f"📥 Ответ от Platega (Status {response.status_code}): {raw_text}")

                if response.status_code >= 400:
                    return {"success": False, "error": f"HTTP {response.status_code}: {raw_text}"}

                try:
                    data = response.json()
                except Exception as e:
                    logger.error(f"❌ Не удалось распарсить JSON от Platega: {e}. Сырой ответ: {raw_text}")
                    return {"success": False, "error": "Сервер вернул не JSON"}

                if data.get("success") or data.get("status") == "success":
                    payment_url = data.get("url") or data.get("redirect") or data.get("paymentUrl")

                    if not payment_url:
                        logger.error(f"❌ В успешном ответе нет URL. Ответ: {data}")
                        return {"success": False, "error": "Платежная система не вернула ссылку на оплату"}

                    return {
                        "success": True,
                        "transaction_id": data.get("id") or data.get("transactionId"),
                        "payment_url": payment_url,
                        "amount": amount
                    }
                else:
                    err_msg = data.get("message") or data.get("error") or "Неизвестная ошибка API"
                    logger.error(f"❌ Ошибка API Platega: {err_msg}")
                    return {"success": False, "error": err_msg}

        except Exception as e:
            logger.error(f"❌ Сетевая ошибка при запросе к Platega: {e}")
            return {"success": False, "error": str(e)}

    def verify_webhook_signature(self, payload: dict, received_signature: str) -> bool:
        """Проверяет подпись вебхука"""
        try:
            shop_id = str(payload.get("shopId") or payload.get("merchantId") or "")
            amount_data = payload.get("paymentDetails", {})
            amount = str(amount_data.get("amount") or payload.get("amount") or "")
            order_id = str(payload.get("orderId") or payload.get("order_id") or "")

            message = f"{shop_id}{amount}{order_id}"
            expected_signature = hashlib.md5((message + self.secret).encode('utf-8')).hexdigest()

            is_valid = (received_signature == expected_signature)
            if not is_valid:
                logger.warning(
                    f"⚠️ Неверная подпись вебхука! Ожидалось: {expected_signature}, получено: {received_signature}")

            return is_valid
        except Exception as e:
            logger.error(f"❌ Ошибка проверки подписи вебхука: {e}")
            return False


# Экземпляр клиента
platega = PlategaClient()