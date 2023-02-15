import ipaddress
import json
import logging
import re
import time
from json import JSONDecodeError

import aiohttp
from api.appd.AppDController import AppdController
from api.Result import Result
from uplink import AiohttpClient
from uplink.auth import BasicAuth, MultiAuth, ProxyAuth
from util.asyncio_utils import AsyncioUtils


class AppDService:
    controller: AppdController

    def __init__(
            self,
            host: str,
            port: int,
            ssl: bool,
            account: str,
            username: str,
            pwd: str,
            verifySsl: bool = True,
            useProxy: bool = False,
            applicationFilter: dict = None,
            timeRangeMins: int = 1440,
    ):
        logging.debug(f"{host} - Initializing controller service")
        connection_url = f'{"https" if ssl else "http"}://{host}:{port}'
        auth = BasicAuth(f"{username}@{account}", pwd)
        self.host = host
        self.username = username
        self.applicationFilter = applicationFilter
        self.timeRangeMins = timeRangeMins
        self.endTime = int(round(time.time() * 1000))
        self.startTime = self.endTime - (1 * 60 * self.timeRangeMins * 1000)

        cookie_jar = aiohttp.CookieJar()
        try:
            if ipaddress.ip_address(host):
                logging.warning(f"Configured host {host} is an IP address. Consider using the DNS instead.")
                logging.warning(f"RFC 2109 explicitly forbids cookie accepting from URLs with IP address instead of DNS name.")
                logging.warning(f"Using unsafe Cookie Jar.")
                cookie_jar = aiohttp.CookieJar(unsafe=True)
        except ValueError:
            pass

        connector = aiohttp.TCPConnector(limit=AsyncioUtils.concurrent_connections, verify_ssl=verifySsl)
        self.session = aiohttp.ClientSession(connector=connector, trust_env=useProxy, cookie_jar=cookie_jar)

        self.controller = AppdController(
            base_url=connection_url,
            auth=auth,
            client=AiohttpClient(session=self.session),
        )
        self.totalCallsProcessed = 0

    def __json__(self):
        return {
            "host": self.host,
            "username": self.username,
        }

    async def loginToController(self) -> Result:
        logging.debug(f"{self.host} - Attempt controller connection.")
        try:
            response = await self.controller.login()
        except Exception as e:
            logging.error(f"{self.host} - Controller login failed with {e}")
            return Result(
                None,
                Result.Error(f"{self.host} - {e}."),
            )
        if response.status_code != 200:
            logging.error(f"{self.host} - Controller login failed with {response.status_code}. Check username and password.")
            return Result(
                response,
                Result.Error(f"{self.host} - Controller login failed with {response.status_code}. Check username and password."),
            )
        try:
            jsessionid = re.search("JSESSIONID=(\\w|\\d)*", str(response.headers)).group(0).split("JSESSIONID=")[1]
            self.controller.jsessionid = jsessionid
        except AttributeError:
            logging.debug(f"{self.host} - Unable to find JSESSIONID in login response. Please verify credentials.")
        try:
            xcsrftoken = re.search("X-CSRF-TOKEN=(\\w|\\d)*", str(response.headers)).group(0).split("X-CSRF-TOKEN=")[1]
            self.controller.xcsrftoken = xcsrftoken
        except AttributeError:
            logging.debug(f"{self.host} - Unable to find X-CSRF-TOKEN in login response. Please verify credentials.")

        if self.controller.jsessionid is None or self.controller.xcsrftoken is None:
            return Result(
                response,
                Result.Error(f"{self.host} - Valid authentication headers not cached from previous login call. Please verify credentials."),
            )

        self.controller.session.headers["X-CSRF-TOKEN"] = self.controller.xcsrftoken
        self.controller.session.headers["Set-Cookie"] = f"JSESSIONID={self.controller.jsessionid};X-CSRF-TOKEN={self.controller.xcsrftoken};"
        self.controller.session.headers["Content-Type"] = "application/json;charset=UTF-8"

        logging.debug(f"{self.host} - Controller initialization successful.")
        return Result(self.controller, None)

    async def getApmApplications(self) -> Result:
        debugString = f"Gathering applications"
        logging.debug(f"{self.host} - {debugString}")

        if self.applicationFilter is not None:
            if self.applicationFilter.get("apm") is None:
                logging.warning(f"Filtered out all APM applications from analysis by match rule {self.applicationFilter['apm']}")
                return Result([], None)

        response = await self.controller.getApmApplications()
        result = await self.getResultFromResponse(response, debugString)
        # apparently it's possible to have a null application name, the controller converts the null into "null"
        if result.error is None:
            for application in result.data:
                if application["name"] is None:
                    application["name"] = "null"

        if self.applicationFilter is not None:
            pattern = re.compile(self.applicationFilter["apm"])
            for application in result.data:
                if not pattern.search(application["name"]):
                    logging.debug(f"Filtered out APM application {application['name']} from analysis by match rule {self.applicationFilter['apm']}")
            result.data = [application for application in result.data if pattern.search(application["name"])]

        return result

    async def getApplicationsAllTypes(self) -> Result:
        debugString = f"Gathering all applications"
        logging.debug(f"{self.host} - {debugString}")
        response = await self.controller.getApplicationsAllTypes()
        return await self.getResultFromResponse(response, debugString)

    async def getMetricData(
            self,
            applicationID: int,
            metric_path: str,
            rollup: bool,
            time_range_type: str,
            duration_in_mins: int = "",
            start_time: int = "",
            end_time: int = 1440,
    ) -> Result:
        debugString = f'Gathering Metrics for:"{metric_path}" on application:{applicationID}'
        logging.debug(f"{self.host} - {debugString}")
        response = await self.controller.getMetricData(
            applicationID,
            metric_path,
            rollup,
            time_range_type,
            duration_in_mins,
            start_time,
            end_time,
        )
        return await self.getResultFromResponse(response, debugString)

    async def getEumApplications(self) -> Result:
        debugString = f"Gathering BRUM Applications"
        logging.debug(f"{self.host} - {debugString}")

        if self.applicationFilter is not None:
            if self.applicationFilter.get("brum") is None:
                logging.warning(f"Filtered out all BRUM applications from analysis by match rule {self.applicationFilter['brum']}")
                return Result([], None)

        response = await self.controller.getEumApplications(f"Custom_Time_Range.BETWEEN_TIMES.{self.endTime}.{self.startTime}.{self.timeRangeMins}")
        result = await self.getResultFromResponse(response, debugString)

        if self.applicationFilter is not None:
            pattern = re.compile(self.applicationFilter["brum"])
            for application in result.data:
                if not pattern.search(application["name"]):
                    logging.debug(
                        f"Filtered out BRUM application {application['name']} from analysis by match rule {self.applicationFilter['brum']}"
                    )
            result.data = [application for application in result.data if pattern.search(application["name"])]

        return result

    async def getMRUMApplications(self) -> Result:
        debugString = f"Gathering MRUM Applications"
        logging.debug(f"{self.host} - {debugString}")

        if self.applicationFilter is not None:
            if self.applicationFilter.get("mrum") is None:
                logging.warning(f"Filtered out all MRUM applications from analysis by match rule {self.applicationFilter['mrum']}")
                return Result([], None)

        response = await self.controller.getMRUMApplications(f"Custom_Time_Range.BETWEEN_TIMES.{self.endTime}.{self.startTime}.{self.timeRangeMins}")
        result = await self.getResultFromResponse(response, debugString)

        tempData = result.data.copy()
        result.data.clear()
        for mrumApplicationGroup in tempData:
            for mrumApplication in mrumApplicationGroup["children"]:
                mrumApplication["name"] = mrumApplication["internalName"]
                mrumApplication["taggedName"] = f"{mrumApplicationGroup['appKey']}-{mrumApplication['name']}"
                result.data.append(mrumApplication)

        if self.applicationFilter is not None:
            pattern = re.compile(self.applicationFilter["mrum"])
            for application in result.data:
                if not pattern.search(application["name"]):
                    logging.debug(
                        f"Filtered out MRUM application {application['name']} from analysis by match rule {self.applicationFilter['mrum']}"
                    )
            result.data = [application for application in result.data if pattern.search(application["name"])]

        return result

    async def close(self):
        logging.debug(f"{self.host} - Closing connection")
        await self.session.close()

    async def getResultFromResponse(self, response, debugString, isResponseJSON=True, isResponseList=True) -> Result:
        body = (await response.content.read()).decode("ISO-8859-1")
        self.totalCallsProcessed += 1

        if response.status_code >= 400:
            msg = f"{self.host} - {debugString} failed with code:{response.status_code} body:{body}"
            try:
                responseJSON = json.loads(body)
                if "message" in responseJSON:
                    msg = f"{self.host} - {debugString} failed with code:{response.status_code} body:{responseJSON['message']}"
            except JSONDecodeError:
                pass
            logging.debug(msg)
            return Result([] if isResponseList else {}, Result.Error(f"{response.status_code}"))
        if isResponseJSON:
            try:
                return Result(json.loads(body), None)
            except JSONDecodeError:
                msg = f"{self.host} - {debugString} failed to parse json from body. Returned code:{response.status_code} body:{body}"
                logging.error(msg)
                return Result([] if isResponseList else {}, Result.Error(msg))
        else:
            return Result(body, None)
