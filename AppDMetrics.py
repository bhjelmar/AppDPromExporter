import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from prometheus_client import Gauge

from api.appd.AppDService import AppDService
from util.asyncio_utils import AsyncioUtils
from util.stdlib_utils import isBase64, base64Encode, base64Decode


@dataclass
class AppDMetric:
    entity_type: str
    metric_path: str
    metric_name: str
    labels: list[str]

    def to_prom_metric(self):
        metric_path = self.metric_path.replace("*", "{}").lower()
        metric_path = self.entity_type.lower() + ":" + metric_path.format(*[label.upper() for label in self.labels])
        return "".join([c if c.isalnum() or c == ":" else "_" for c in metric_path])


class AppDMetrics:
    def __init__(self, concurrent_connections: int, job_file: str, mapping_file: str):
        if not Path(f"input/{job_file}.json").exists():
            logging.error(f"Job file {job_file} does not exist")
            sys.exit(1)
        if not Path(f"input/{mapping_file}.tsv").exists():
            logging.error(f"Mapping file {mapping_file} does not exist")
            sys.exit(1)

        self.job = json.loads(open(f"input/{job_file}.json").read())

        # Default concurrent connections to 10 for On-Premise controllers
        if any(job for job in self.job if "saas.appdynamics.com" not in job["host"]):
            logging.info(f"On-Premise controller detected. It is recommended to use a maximum of 10 concurrent connections.")
            concurrent_connections = 10 if concurrent_connections is None else concurrent_connections
        else:
            logging.info(f"SaaS controller detected. It is recommended to use a maximum of 50 concurrent connections.")
            concurrent_connections = 50 if concurrent_connections is None else concurrent_connections
        AsyncioUtils.init(concurrent_connections)

        # Convert passwords to base64 if they aren't already
        encoding_prefix = "ENCODED"
        for controller in self.job:
            if not isBase64(controller["pwd"]):
                controller["pwd"] = base64Encode(f"{encoding_prefix}-{controller['pwd']}")
            elif not base64Decode(controller["pwd"]).startswith(f"{encoding_prefix}-"):
                controller["pwd"] = base64Encode(f"{encoding_prefix}-{controller['pwd']}")

        # Save the job back to disk with the updated password
        self.refreshIntervalMinutes = self.job[0]["refreshIntervalMinutes"]
        with open(f"input/{job_file}.json", "w", encoding="ISO-8859-1") as f:
            json.dump(
                self.job,
                fp=f,
                ensure_ascii=False,
                indent=4,
            )

        # Instantiate controllers
        self.controllers = [
            AppDService(
                host=controller["host"],
                port=controller["port"],
                ssl=controller["ssl"],
                account=controller["account"],
                username=controller["username"],
                pwd=base64Decode(controller["pwd"])[len(f"{encoding_prefix}-"):],
                verifySsl=controller.get("verifySsl", True),
                useProxy=controller.get("useProxy", False),
                applicationFilter=controller.get("applicationFilter", None),
                timeRangeMins=controller.get("refreshIntervalMinutes", 1),
            )
            for controller in self.job
        ]

        self.metrics = []
        metrics_tsv = open(f"input/{mapping_file}.tsv").read()
        appd_metrics = []
        for line in metrics_tsv.split("\n")[1:]:
            if line:
                line = line.replace('"', "").split("\t")
                labels = line[3].split(",")
                line[3] = labels if labels != [""] else []
                appd_metrics.append(AppDMetric(*line))

        for metric in appd_metrics:
            logging.info(f"Registering metric: {metric.to_prom_metric()}")
            gauge = Gauge(
                name=metric.to_prom_metric(),
                documentation=metric.metric_name,
                labelnames=["controller", "application", *metric.labels],
            )
            self.metrics.append((metric, gauge))

    async def run_metrics_loop(self):
        while True:
            start = time.time()
            await self.fetch()
            end = time.time()
            logging.info(f"Metrics loop completed in {end - start} seconds")
            seconds_to_sleep = self.refreshIntervalMinutes * 60 - (end - start)

            if seconds_to_sleep < 0:
                logging.warning(f"Metrics loop took longer than the refresh interval. Skipping sleep.")
                logging.warning(
                    f"Consider increasing refreshIntervalMinutes from {self.refreshIntervalMinutes} to at least {(int(end - start) // 60) + 1}")
                continue

            logging.info(f"Sleeping for {seconds_to_sleep} seconds")
            await AsyncioUtils.sleep(seconds_to_sleep)

    async def fetch(self):
        loginFutures = [controller.loginToController() for controller in self.controllers]
        loginResults = await AsyncioUtils.gatherWithConcurrency(*loginFutures)
        if any(login.error is not None for login in loginResults):
            await self.abortAndCleanup(f"Unable to connect to one or more controllers. Aborting.")

        apmApplicationsFutures = [controller.getApmApplications() for controller in self.controllers]
        apmApplicationsResults = await AsyncioUtils.gatherWithConcurrency(*apmApplicationsFutures)
        if any(apmApplications.error is not None for apmApplications in apmApplicationsResults):
            await self.abortAndCleanup(f"Unable to retrieve APM applications from one or more controllers. Aborting.")

        brumApplicationsFutures = [controller.getEumApplications() for controller in self.controllers]
        brumApplicationsResults = await AsyncioUtils.gatherWithConcurrency(*brumApplicationsFutures)
        if any(brumApplications.error is not None for brumApplications in brumApplicationsResults):
            await self.abortAndCleanup(f"Unable to retrieve BRUM applications from one or more controllers. Aborting.")

        mrumApplicationsFutures = [controller.getMRUMApplications() for controller in self.controllers]
        mrumApplicationsResults = await AsyncioUtils.gatherWithConcurrency(*mrumApplicationsFutures)
        if any(mrumApplications.error is not None for mrumApplications in mrumApplicationsResults):
            await self.abortAndCleanup(f"Unable to retrieve MRUM applications from one or more controllers. Aborting.")

        extendedApplicationsFutures = [controller.getApplicationsAllTypes() for controller in self.controllers]
        extendedApplicationsResults = await AsyncioUtils.gatherWithConcurrency(*extendedApplicationsFutures)
        if any(extendedApplications.error is not None for extendedApplications in extendedApplicationsResults):
            await self.abortAndCleanup(f"Unable to retrieve extended applications from one or more controllers. Aborting.")

        for idx, controller in enumerate(self.controllers):
            apmApplications = apmApplicationsResults[idx].data
            brumApplications = brumApplicationsResults[idx].data
            mrumApplications = mrumApplicationsResults[idx].data
            extendedApplications = extendedApplicationsResults[idx].data

            metrics_to_fetch = self.metrics
            i = 0
            for metric, gauge in metrics_to_fetch:
                logging.info(f"Fetching metric: {metric.to_prom_metric()} ({i + 1}/{len(metrics_to_fetch)})")
                i += 1

                if metric.entity_type == "APM":
                    root = apmApplications
                elif metric.entity_type == "ANALYTICS":
                    root = [extendedApplications["analyticsApplication"]]
                elif metric.entity_type == "DATABASE":
                    root = [extendedApplications["dbMonApplication"]]
                elif metric.entity_type == "BRUM":
                    root = brumApplications
                elif metric.entity_type == "MRUM":
                    for app in mrumApplications:
                        app["id"] = app["applicationId"]
                    root = mrumApplications
                elif metric.entity_type == "SIM":
                    root = [extendedApplications["simApplication"]]
                else:
                    logging.error(f"Unknown entity type: {metric.entity_type}")
                    continue

                metric_data_futures = [controller.getMetricData(
                    entity["id"],
                    metric.metric_path,
                    rollup=True,
                    time_range_type="BEFORE_NOW",
                    duration_in_mins=controller.timeRangeMins,
                ) for entity in root]
                metric_data_results = await AsyncioUtils.gatherWithConcurrency(*metric_data_futures)

                for entity, metric_data in zip(root, metric_data_results):
                    if metric_data.error:
                        logging.error(f"Error fetching metric: {metric.to_prom_metric()} for entity: {entity['name']}")
                    if metric_data.error is None and metric_data.data:
                        # for each wildcard index, parse the returned metric path and add the label
                        # e.g. my|metric|path|*|* will return something like my|metric|path|label1|label2
                        wildcard_indices = [i for i, x in enumerate(metric.metric_path.split("|")) if x == "*"]
                        for labeled_metric in metric_data.data:
                            if labeled_metric["metricValues"]:
                                value = labeled_metric["metricValues"][0]["value"]
                                labels = []
                                for index in wildcard_indices:
                                    labels.append(labeled_metric["metricPath"].split("|")[index])
                                logging.debug(f"Setting metric: {metric.to_prom_metric()} with labels: {labels} to value: {value}")
                                gauge.labels(controller.host, entity["name"], *labels).set(value)

    async def abortAndCleanup(self, msg: str, error=True):
        """Closes open controller connections"""
        await AsyncioUtils.gatherWithConcurrency(*[controller.close() for controller in self.controllers])
        if error:
            logging.error(msg)
            sys.exit(1)
        else:
            if msg:
                logging.info(msg)
            sys.exit(0)
