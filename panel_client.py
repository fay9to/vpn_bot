# panel_client.py
import httpx
import json
import re
from typing import Optional, Dict, Any, List
import config
import logging

logger = logging.getLogger(__name__)


class XUIPanelClient:
    def __init__(self):
        self.base_url = config.PANEL_URL.rstrip('/')
        self.api_url = f"{self.base_url}/panel/api"
        self.token = config.API_TOKEN
        logger.info(f"✅ Panel URL: {self.base_url}")
        logger.info(f"✅ API URL: {self.api_url}")

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Универсальный метод для запросов к API"""
        url = f"{self.api_url}/{endpoint}"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=30.0,
                    verify=False
            ) as client:
                response = await client.request(method, url, headers=headers, **kwargs)

                if response.status_code != 200:
                    logger.error(f"API error [{method} {endpoint}]: {response.status_code} - {response.text[:200]}")
                    return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}

                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    return {"success": False, "error": f"Invalid JSON: {response.text[:200]}"}
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {"success": False, "error": str(e)}

    async def add_client(self, email: str, inbound_ids: List[int],
                         expiry_time: int = 0,
                         total_gb: int = 0,
                         limit_ip: int = 0,
                         enable: bool = True) -> Optional[Dict[str, Any]]:
        """Создаёт клиента с лимитом IP и трафика"""
        client_data = {
            "email": email,
            "totalGB": total_gb,
            "expiryTime": expiry_time,
            "tgId": 0,
            "limitIp": limit_ip,
            "enable": enable
        }

        payload = {
            "client": client_data,
            "inboundIds": inbound_ids
        }

        logger.info(f"Creating client {email} with inbounds {inbound_ids}, limitIp={limit_ip}, totalGB={total_gb}")
        result = await self._request("POST", "clients/add", json=payload)

        if result.get("success"):
            logger.info(f"✅ Successfully created client {email}")
            return {"success": True, "email": email}

        logger.error(f"❌ Failed to create client: {result}")
        return None

    async def get_client_info(self, email: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о клиенте включая subId"""
        logger.info(f"Getting client info for {email}")
        result = await self._request("GET", f"clients/get/{email}")

        if result.get("success") and result.get("obj"):
            return result.get("obj")

        logger.warning(f"Client info not found for {email}")
        return None

    async def update_client(self, email: str, **kwargs) -> bool:
        """Обновляет клиента"""
        result = await self._request("POST", f"clients/update/{email}", json=kwargs)
        return result.get("success", False)

    async def delete_client(self, email: str) -> bool:
        """Удаляет клиента"""
        result = await self._request("POST", f"clients/del/{email}")
        return result.get("success", False)

    async def get_client_traffic(self, email: str) -> Optional[Dict[str, Any]]:
        """Получает статистику трафика клиента"""
        client_info = await self.get_client_info(email)
        if not client_info:
            return None

        client_data = client_info.get("client", {})
        return {
            "up": client_data.get("up", 0) or 0,
            "down": client_data.get("down", 0) or 0,
            "total": client_data.get("totalGB", 0) or 0
        }

    async def reset_client_traffic(self, email: str) -> bool:
        """Сбрасывает трафик клиента"""
        result = await self._request("POST", f"clients/resetTraffic/{email}")
        return result.get("success", False)

    async def get_client_ips(self, email: str) -> Optional[List[str]]:
        """Получает IP-адреса клиента"""
        result = await self._request("POST", f"clients/ips/{email}")

        if result.get("success") and result.get("obj"):
            return result.get("obj")

        return None

    async def clear_client_ips(self, email: str) -> bool:
        """Очищает IP-адреса клиента"""
        result = await self._request("POST", f"clients/clearIps/{email}")
        return result.get("success", False)

    async def add_client_to_all_inbounds(self, email: str,
                                         expiry_time: int = 0,
                                         total_gb: int = 0,
                                         limit_ip: int = 0) -> bool:
        """Добавляет клиента ко всем inbound'ам"""
        inbound_ids = [inbound["id"] for inbound in config.ALL_INBOUNDS]

        logger.info(f"Adding client {email} to all inbounds: {inbound_ids}, limitIp={limit_ip}, totalGB={total_gb}")

        result = await self.add_client(
            email=email,
            inbound_ids=inbound_ids,
            expiry_time=expiry_time,
            total_gb=total_gb,
            limit_ip=limit_ip,
            enable=True
        )

        return result is not None and result.get("success", False)

    async def get_subscription_link(self, email: str) -> Optional[str]:
        """Получает правильную ссылку подписки с subId"""
        logger.info(f"Getting subscription link for {email}")

        client_info = await self.get_client_info(email)

        if not client_info:
            logger.warning(f"Client {email} not found")
            return None

        # subId находится внутри client_info["client"]["subId"]
        client_data = client_info.get("client", {})
        sub_id = client_data.get("subId")

        logger.info(f"Client data: {client_data}")
        logger.info(f"subId: {sub_id}")

        if not sub_id:
            logger.warning(f"subId not found, using email as fallback")
            sub_id = email

        # Извлекаем хост из PANEL_URL
        match = re.match(r'https?://([^:/]+)', config.PANEL_URL)
        if not match:
            logger.error(f"Cannot extract host from PANEL_URL")
            return None

        host = match.group(1)
        sub_port = getattr(config, 'SUBSCRIPTION_PORT', 2096)

        sub_link = f"http://{host}:{sub_port}/sub/{sub_id}"
        logger.info(f"✅ Subscription link: {sub_link}")

        return sub_link

    async def get_client_links(self, email: str) -> Dict[str, str]:
        """Получает ссылки для всех локаций"""
        result = await self._request("GET", f"clients/links/{email}")
        links = {}

        if result.get("success") and result.get("obj"):
            client_links = result.get("obj")
            for i, link in enumerate(client_links):
                if i < len(config.ALL_INBOUNDS):
                    links[config.ALL_INBOUNDS[i]["name"]] = link

        return links