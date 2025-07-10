import httpx
import math
from datetime import datetime
from pydantic import BaseModel
from loguru import logger
from thefuzz import process


from models import SettingModel


class PackageInfoModel(BaseModel):
    name: str
    author: str
    description: str = ""
    description_type: str = "text/markdown"
    versions: list[str] = []


class DependenceManager:
    def __init__(self):
        self.url = "https://pypi.org"
        self.dependencies = []
        self.client = httpx.AsyncClient()

    async def packages_update(self) -> bool:
        dep_db_res = await SettingModel.find_one(SettingModel.name == "dependencies")
        if not dep_db_res:
            await SettingModel(
                name="dependencies",
                data=[],
                create_at=datetime.now(),
                update_at=datetime.now(),
            ).insert()
        self.dependencies = []
        dep_res = await self.client.get(
            url=self.url + "/simple/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        )
        if dep_res.status_code == 200:
            dep_list = [i["name"] for i in dep_res.json()["projects"]]
            for i in range(1, math.ceil(len(dep_list) / 5000)):
                insert_list = dep_list[(i - 1) * 1000 : i * 1000]
                await SettingModel.find_one(SettingModel.name == "dependencies").update(
                    {"$push": {"data": {"$each": insert_list}}}
                )
            return True
        else:
            logger.error("Dependencies update failed.")
            return False

    async def package_search(self, name: str) -> list[str]:
        pkg_res = await self.client.get(
            url=self.url + "/simple/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        )
        if pkg_res.status_code == 200:
            pkg_json = pkg_res.json()
            pkg_list = []
            for pkg in pkg_json["projects"]:
                if name in pkg["name"]:
                    pkg_list.append(pkg["name"])
            pkg_list = [p[0] for p in process.extract(name, pkg_list, limit=20)]
            return pkg_list
        else:
            return []

    async def package_info(self, name: str) -> dict:
        dep_res = await self.client.get(
            f"{self.url}/pypi/{name}/json",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        )
        if dep_res.status_code == 200:
            pkj_json = dep_res.json()
            return {
                "name": name,
                "author": pkj_json["info"]["author"],
                "description": pkj_json["info"]["description"],
                "description_type": pkj_json["info"]["description_content_type"],
                "versions": list(pkj_json["releases"].keys())[::-1],
            }
        else:
            return {}

    async def package_add(self, appid: str, name: str, version: str):
        return


dependence_manager = DependenceManager()
