# platega_client.py
import httpx
import hmac
import logging
import config

logger = logging.getLogger(__name__)


class PlategaClient:
    """
    Клиент для Platega API (https://docs.platega.io).

    Авторизация — только через заголовки X-MerchantId / X-Secret.
    Единственный эндпоинт создания платежа: POST /transaction/process
    (версионирования v1/v2 в API нет).
    """

    def __init__(self):
        self.merchant_id = config.PLATEGA_MERCHANT_ID
        self.secret = config.PLATEGA_SECRET
        self.base_url = (config.PLATEGA_BASE_URL or "https://app.platega.io").rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(config.PLATEGA_ENABLED and self.merchant_id and self.secret)

    def _headers(self) -> dict:
        return {
            "X-MerchantId": self.merchant_id or "",
            "X-Secret": self.secret or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_payment(
            self,
            amount: float,
            description: str,
            payload: str = "",
            payment_method: int = 11,  # 11 = Карточный эквайринг
    ) -> dict:
        """
        payload — наша внутренняя метка (например, order_id), которую Platega
        сохранит и вернёт в GET /transaction/{id} (но НЕ в вебхуке!).
        Поэтому основной ключ для сопоставления платежа — transactionId,
        который возвращается в этом ответе и который нужно сохранить у себя.
        """
        if not self.is_configured:
            return {"success": False, "error": "Platega не настроен: проверьте PLATEGA_ENABLED / PLATEGA_MERCHANT_ID / PLATEGA_SECRET в .env"}

        url = f"{self.base_url}/transaction/process"

        body = {
            "paymentMethod": payment_method,
            "paymentDetails": {
                "amount": round(amount, 2),
                "currency": "RUB",
            },
            "description": description[:64],
        }
        if config.PLATEGA_RETURN_URL:
            body["return"] = config.PLATEGA_RETURN_URL
        if config.PLATEGA_FAILED_URL:
            body["failedUrl"] = config.PLATEGA_FAILED_URL
        if payload:
            body["payload"] = payload

        try:
            logger.info(f"🎯 Запрос к Platega: {url}")
            logger.info(f"📤 Payload: {body}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=body, headers=self._headers())

                raw_text = response.text
                logger.info(f"📥 Ответ от Platega (Status {response.status_code}): {raw_text}")

                if response.status_code >= 400:
                    return {"success": False, "error": f"HTTP {response.status_code}: {raw_text}"}

                try:
                    data = response.json()
                except Exception as e:
                    logger.error(f"❌ Не удалось распарсить JSON от Platega: {e}. Сырой ответ: {raw_text}")
                    return {"success": False, "error": "Сервер вернул не JSON"}

                transaction_id = data.get("transactionId")
                payment_url = data.get("redirect")

                if not transaction_id or not payment_url:
                    logger.error(f"❌ В ответе нет transactionId/redirect. Ответ: {data}")
                    return {"success": False, "error": "Платёжная система вернула неполный ответ"}

                # paymentDetails в ответе — строка вида "86.11 RUB": это итоговая сумма
                # С УЖЕ включённой комиссией платёжного метода (её считает сама Platega).
                gross_amount = amount
                payment_details_raw = data.get("paymentDetails")
                if isinstance(payment_details_raw, str):
                    try:
                        gross_amount = float(payment_details_raw.split()[0])
                    except (ValueError, IndexError):
                        pass

                return {
                    "success": True,
                    "transaction_id": transaction_id,
                    "payment_url": payment_url,
                    "amount": amount,
                    "gross_amount": gross_amount,
                    "expires_in": data.get("expiresIn"),
                }

        except Exception as e:
            logger.error(f"❌ Сетевая ошибка при запросе к Platega: {e}")
            return {"success": False, "error": str(e)}

    async def get_transaction(self, transaction_id: str) -> dict | None:
        """GET /transaction/{id} — статус и детали транзакции (включает наш payload)."""
        if not self.is_configured or not transaction_id:
            return None

        url = f"{self.base_url}/transaction/{transaction_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=self._headers())
                if response.status_code >= 400:
                    logger.error(f"❌ Platega get_transaction HTTP {response.status_code}: {response.text}")
                    return None
                return response.json()
        except Exception as e:
            logger.error(f"❌ Ошибка запроса статуса Platega: {e}")
            return None

    def verify_webhook_auth(self, headers) -> bool:
        """
        Вебхук Platega аутентифицируется заголовками X-MerchantId / X-Secret,
        а не подписью тела запроса. Сравниваем через hmac.compare_digest
        (защита от timing-атак).
        """
        received_merchant_id = headers.get("X-MerchantId", "") or headers.get("x-merchantid", "")
        received_secret = headers.get("X-Secret", "") or headers.get("x-secret", "")

        return bool(
            self.merchant_id and self.secret
            and hmac.compare_digest(received_merchant_id, self.merchant_id)
            and hmac.compare_digest(received_secret, self.secret)
        )


# Экземпляр клиента
platega = PlategaClient()